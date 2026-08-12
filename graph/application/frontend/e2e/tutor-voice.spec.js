import { expect, test } from '@playwright/test'

const tutorUrl = 'http://127.0.0.1:8600'

async function installVoiceBrowserMocks(page) {
  await page.addInitScript(() => {
    try {
      localStorage.setItem('adaptive_tutor_voice_consent', 'true')
      localStorage.setItem('adaptive_tutor_voice_auto_speak', 'true')
    } catch (_error) {
      // The script also runs for the initial opaque document.
    }

    const state = {
      recorderStarts: 0,
      trackStops: 0,
      audioPlays: 0,
      audioPauses: 0,
      createdUrls: [],
      revokedUrls: []
    }
    window.__voiceTest = state
    window.__voiceSupportedMime = 'audio/webm'

    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: async () => {
          const track = {
            readyState: 'live',
            stop() {
              if (this.readyState === 'ended') return
              this.readyState = 'ended'
              state.trackStops += 1
            }
          }
          return { getTracks: () => [track] }
        }
      }
    })

    class MockMediaRecorder {
      static isTypeSupported(type) {
        return type.startsWith(window.__voiceSupportedMime)
      }

      constructor(stream, options = {}) {
        this.stream = stream
        this.mimeType = options.mimeType || 'audio/webm'
        this.state = 'inactive'
        this.ondataavailable = null
        this.onerror = null
        this.onstop = null
      }

      start() {
        this.state = 'recording'
        state.recorderStarts += 1
      }

      stop() {
        if (this.state === 'inactive') return
        this.state = 'inactive'
        this.ondataavailable?.({
          data: new Blob(['mock-opus-audio'], { type: this.mimeType })
        })
        queueMicrotask(() => this.onstop?.())
      }
    }
    Object.defineProperty(window, 'MediaRecorder', {
      configurable: true,
      value: MockMediaRecorder
    })

    class MockAudio {
      constructor(url) {
        this.url = url
        this.currentTime = 0
        this.onended = null
        this.onerror = null
      }

      play() {
        state.audioPlays += 1
        return Promise.resolve()
      }

      pause() {
        state.audioPauses += 1
      }
    }
    Object.defineProperty(window, 'Audio', { configurable: true, value: MockAudio })

    URL.createObjectURL = () => {
      const url = `blob:voice-test-${state.createdUrls.length + 1}`
      state.createdUrls.push(url)
      return url
    }
    URL.revokeObjectURL = url => state.revokedUrls.push(url)
  })
}

async function mockTutorApi(page, historyItems = [], { chatDelayMs = 0 } = {}) {
  const calls = {
    chat: [],
    speech: [],
    transcriptions: 0,
    transcriptionBodies: [],
    resets: 0
  }

  await page.route(`${tutorUrl}/api/**`, async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname

    if (path === '/api/voice/capabilities') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          enabled: true,
          transcription: true,
          speech: true,
          audio_types: ['audio/m4a', 'audio/mp4', 'audio/ogg', 'audio/wav', 'audio/webm']
        })
      })
    }
    if (path === '/api/voice/transcriptions') {
      calls.transcriptions += 1
      calls.transcriptionBodies.push(request.postData() || '')
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ text: '请讲讲动态规划', request_id: 'transcription-test' })
      })
    }
    if (path === '/api/voice/speech') {
      calls.speech.push(request.postDataJSON())
      return route.fulfill({
        status: 200,
        contentType: 'audio/mpeg',
        body: Buffer.from([73, 68, 51, 4, 0, 0])
      })
    }
    if (path === '/api/chat') {
      calls.chat.push(request.postDataJSON())
      if (chatDelayMs) await new Promise(resolve => setTimeout(resolve, chatDelayMs))
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ reply: '动态规划会复用子问题的答案。', tools: [] })
      })
    }
    if (path === '/api/chat/history') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ student: url.searchParams.get('student'), items: historyItems })
      })
    }
    if (/^\/api\/learners\/[^/]+\/state$/.test(path)) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ revision: 0, profile: { nodes: [], mastered: [] } })
      })
    }
    if (/^\/api\/learners\/[^/]+\/dashboard$/.test(path)) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ summary: { mastered: 0, total: 0 } })
      })
    }
    if (path === '/api/reset') {
      calls.resets += 1
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true })
      })
    }
    return route.fulfill({ status: 404, body: 'not mocked' })
  })

  return calls
}

test.beforeEach(async ({ page }) => {
  await installVoiceBrowserMocks(page)
})

async function startDigitalHuman(page) {
  const playButton = page.locator('#digitalHumanPlay')
  await expect(playButton).toBeVisible()
  await playButton.click()
  await expect.poll(() => page.evaluate(() => {
    const video = document.querySelector('#digitalHumanVideo')
    return Boolean(video && !video.paused)
  })).toBe(true)
  await expect.poll(() => page.locator('#digitalHumanVideo').evaluate(video => video.currentTime)).toBeGreaterThanOrEqual(2)
  expect(await page.locator('#digitalHumanVideo').evaluate(video => video.muted)).toBe(false)
  await expect(playButton).toBeHidden()
  await expect(page.locator('body')).not.toHaveClass(/intro-active/)
}

test('voice transcript is editable before chat and triggers automatic speech', async ({ page }) => {
  const calls = await mockTutorApi(page)
  await page.goto(`${tutorUrl}?student=voice_e2e`)
  await startDigitalHuman(page)

  const mic = page.locator('#mic')
  await expect(mic).toBeVisible()
  await expect(mic).toBeEnabled()
  await expect(page.locator('#autoSpeak')).toBeChecked()

  await mic.click()
  await expect(mic).toHaveClass(/recording/)
  await expect(page.locator('#voiceStatus')).toContainText('正在录音')

  await mic.click()
  await expect(page.locator('#msg')).toHaveValue('请讲讲动态规划')
  await expect(page.locator('#voiceStatus')).toHaveText('转写完成，请确认文字')
  expect(calls.transcriptions).toBe(1)
  expect(calls.chat).toHaveLength(0)

  await page.locator('#msg').fill('请用例子讲讲动态规划')
  await page.locator('#send').click()

  await expect.poll(() => calls.chat.length).toBe(1)
  expect(calls.chat[0]).toMatchObject({
    student: 'voice_e2e',
    message: '请用例子讲讲动态规划'
  })
  const reply = page.locator('.bubble.ai').last()
  await expect(reply.locator('.bubble-content')).toHaveText('动态规划会复用子问题的答案。')
  await expect.poll(() => calls.speech.length).toBe(1)
  await expect.poll(() => page.evaluate(() => window.__voiceTest.audioPlays)).toBe(1)
  expect(calls.speech[0].text).toBe('动态规划会复用子问题的答案。')

  await reply.getByRole('button', { name: '停止播放' }).click()
  await expect.poll(() => page.evaluate(() => window.__voiceTest.audioPauses)).toBe(1)
  await expect.poll(() => page.evaluate(() => window.__voiceTest.revokedUrls.length)).toBe(1)
})

test('chat waiting animation stays visible until the reply is ready', async ({ page }) => {
  const calls = await mockTutorApi(page, [], { chatDelayMs: 500 })
  await page.goto(`${tutorUrl}?student=waiting_e2e`)
  await startDigitalHuman(page)

  const waitingVideoResponse = page.waitForResponse(response => (
    new URL(response.url()).pathname === '/chat-waiting.mp4'
  ))
  await page.locator('#msg').fill('请讲一下动态规划')
  await page.locator('#send').click()

  const waiting = page.locator('.waiting-bubble')
  await expect(waiting).toBeVisible()
  await expect(waiting.locator('video')).toHaveAttribute('src', 'chat-waiting.mp4')
  expect((await waitingVideoResponse).status()).toBeGreaterThanOrEqual(200)
  expect((await waitingVideoResponse).status()).toBeLessThan(300)
  await expect.poll(() => calls.chat.length).toBe(1)
  await expect(waiting).toHaveCount(0)
  await expect(page.locator('.bubble.ai').last()).toBeVisible()
})

test('iOS-style MP4 recording is selected and uploaded with an MP4 filename', async ({ page }) => {
  await page.addInitScript(() => {
    window.__voiceSupportedMime = 'audio/mp4'
  })
  const calls = await mockTutorApi(page)
  await page.goto(`${tutorUrl}?student=voice_ios`)
  await startDigitalHuman(page)

  const mic = page.locator('#mic')
  await expect(mic).toBeEnabled()
  await mic.click()
  await expect(mic).toHaveClass(/recording/)
  await mic.click()

  await expect.poll(() => calls.transcriptions).toBe(1)
  expect(calls.transcriptionBodies[0]).toMatch(/filename="recording\.mp4"/)
  expect(calls.transcriptionBodies[0]).toContain('Content-Type: audio/mp4')
})

test('recording and playback resources are cleared on navigation boundaries', async ({ page }) => {
  const calls = await mockTutorApi(page, [
    { role: 'assistant', content: '这是一条可朗读的历史回复。', tools: [] }
  ])
  await page.goto(`${tutorUrl}?student=voice_cleanup`)
  await startDigitalHuman(page)

  const reply = page.locator('.bubble.ai').last()
  await reply.getByRole('button', { name: '播放回复' }).click()
  await expect.poll(() => page.evaluate(() => window.__voiceTest.audioPlays)).toBe(1)

  await page.locator('#mic').click()
  await expect.poll(() => page.evaluate(() => window.__voiceTest.audioPauses)).toBe(1)
  await expect(page.locator('#mic')).toHaveClass(/recording/)
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await expect.poll(() => page.evaluate(() => window.__voiceTest.trackStops)).toBe(1)
  await expect(page.locator('#voiceStatus')).toHaveText('语音状态')
  expect(calls.transcriptions).toBe(0)

  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  })
  await reply.getByRole('button', { name: '播放回复' }).click()
  await expect.poll(() => page.evaluate(() => window.__voiceTest.audioPlays)).toBe(2)
  await page.locator('#student').fill('voice_cleanup_next')
  await page.locator('#student').dispatchEvent('change')
  await expect.poll(() => page.evaluate(() => window.__voiceTest.audioPauses)).toBe(2)

  const refreshedReply = page.locator('.bubble.ai').last()
  await refreshedReply.getByRole('button', { name: '播放回复' }).click()
  await expect.poll(() => page.evaluate(() => window.__voiceTest.audioPlays)).toBe(3)
  await page.locator('#reset').click()
  await expect.poll(() => page.evaluate(() => window.__voiceTest.audioPauses)).toBe(3)
  await expect.poll(() => calls.resets).toBe(1)
  await expect(page.locator('.meta')).toContainText('会话已重置')
})
