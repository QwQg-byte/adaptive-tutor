import { expect, test } from '@playwright/test'

const tutorBase = 'http://127.0.0.1:8600/api'

function key(prefix) {
  return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2)}`
}

test('assistant and graph pages share one revisioned learner state', async ({ browser, request }) => {
  const student = `e2e_${Date.now()}`
  const learner = `${tutorBase}/learners/${encodeURIComponent(student)}`

  const initial = await request.get(`${learner}/state`)
  expect(initial.ok()).toBeTruthy()
  expect((await initial.json()).revision).toBe(0)

  const initialPlanResponse = await request.post(`${learner}/plans`, {
    data: {
      target: '动态规划',
      difficulty_preference: 'balanced',
      max_depth: 6,
      questions_per_step: 3,
      expected_revision: 0
    }
  })
  expect(initialPlanResponse.ok()).toBeTruthy()
  const initialPlan = await initialPlanResponse.json()
  const practiceStep = initialPlan.steps.find(step => step.questions?.length)
  expect(practiceStep).toBeTruthy()
  const question = practiceStep.questions[0]
  const initialDashboardResponse = await request.get(`${learner}/dashboard`)
  expect(initialDashboardResponse.ok()).toBeTruthy()
  const initialDashboard = await initialDashboardResponse.json()

  const context = await browser.newContext()
  const assistant = await context.newPage()
  const graph = await context.newPage()

  await assistant.goto(`http://127.0.0.1:8600?student=${encodeURIComponent(student)}`)
  await expect(assistant.locator('#student')).toHaveValue(student)
  await expect(assistant.locator('#trackCount')).toHaveText(
    `0/${initialDashboard.summary.total} 已掌握`
  )
  await assistant.locator('#target').fill(initialPlan.target_id)
  await assistant.locator('#doplan').click()
  const expectedStepNames = initialPlan.steps.map(step => step.name)
  await expect(assistant.locator('#plan .step-name')).toHaveCount(expectedStepNames.length)
  expect(await assistant.locator('#plan .step-name').allTextContents()).toEqual(expectedStepNames)

  await graph.goto(`/path?student=${encodeURIComponent(student)}&target=${encodeURIComponent(initialPlan.target_id)}&auto=1`)
  await expect(graph.getByText('状态 v0', { exact: true })).toBeVisible()
  await expect(graph.locator('.plan-step-name')).toHaveCount(expectedStepNames.length)
  expect(await graph.locator('.plan-step-name').allTextContents()).toEqual(expectedStepNames)

  const wrongResponse = await request.post(`${learner}/attempts`, {
    data: {
      question_id: question.id,
      target_id: initialPlan.target_id,
      path_node_id: practiceStep.id,
      correct: false,
      source_page: 'graph',
      expected_revision: 0,
      idempotency_key: key('wrong')
    }
  })
  expect(wrongResponse.ok()).toBeTruthy()
  const wrong = await wrongResponse.json()
  expect(wrong.revision).toBe(1)

  const [wrongState, wrongMistakes, reviewPlan] = await Promise.all([
    request.get(`${learner}/state`).then(response => response.json()),
    request.get(`${learner}/mistakes?status=open`).then(response => response.json()),
    request.post(`${learner}/plans`, {
      data: { target: initialPlan.target_id, expected_revision: 1 }
    }).then(response => response.json())
  ])
  expect(wrongState.revision).toBe(1)
  expect(wrongMistakes.revision).toBe(1)
  expect(reviewPlan.revision).toBe(1)
  expect(wrongMistakes.items.some(item => item.question_id === question.id)).toBeTruthy()
  const reviewedStep = reviewPlan.steps.find(step => step.id === practiceStep.id)
  expect(reviewedStep?.review_tasks.some(task => task.question_id === question.id)).toBeTruthy()

  await graph.goto(`/mistakes?student=${encodeURIComponent(student)}`)
  await expect(graph.getByText('状态 v1', { exact: true })).toBeVisible()
  await expect(graph.getByText(question.id, { exact: true })).toBeVisible()

  const correctResponse = await request.post(`${learner}/attempts`, {
    data: {
      question_id: question.id,
      target_id: initialPlan.target_id,
      path_node_id: practiceStep.id,
      correct: true,
      source_page: 'graph',
      expected_revision: 1,
      idempotency_key: key('correct')
    }
  })
  expect(correctResponse.ok()).toBeTruthy()
  expect((await correctResponse.json()).mistake.status).toBe('resolved')

  await graph.reload()
  await expect(graph.getByText('状态 v2', { exact: true })).toBeVisible()
  await graph.getByText('已复习', { exact: true }).first().click()
  await expect(graph.getByText(question.id, { exact: true })).toBeVisible()

  const refreshedPlan = await request.post(`${learner}/plans`, {
    data: { target: initialPlan.target_id, expected_revision: 2 }
  }).then(response => response.json())
  const stepToComplete = refreshedPlan.steps[0]
  const completedResponse = await request.put(
    `${learner}/plans/${encodeURIComponent(initialPlan.target_id)}/steps/${encodeURIComponent(stepToComplete.id)}`,
    {
      data: {
        status: 'completed',
        expected_revision: 2,
        idempotency_key: key('complete')
      }
    }
  )
  expect(completedResponse.ok()).toBeTruthy()

  const finalPlan = await request.post(`${learner}/plans`, {
    data: { target: initialPlan.target_id, expected_revision: 3 }
  }).then(response => response.json())
  expect(finalPlan.completed_skipped.some(step => step.id === stepToComplete.id)).toBeTruthy()

  await assistant.bringToFront()
  await assistant.locator('#target').fill(initialPlan.target_id)
  await assistant.locator('#doplan').click()
  await expect(assistant.locator('#plan')).toContainText('当前目标已完成 1 步')

  await context.close()
})

test('student-bound question detail link records wrong and correct attempts', async ({ page, request }) => {
  const student = `question_link_${Date.now()}`
  const learner = `${tutorBase}/learners/${encodeURIComponent(student)}`
  const questionId = 'XY2111'

  await page.goto(
    `/questions?id=${encodeURIComponent(questionId)}&student=${encodeURIComponent(student)}`
  )

  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText(questionId)
  await expect(dialog.getByTestId('record-wrong')).toBeVisible()
  await expect(dialog.getByTestId('record-correct')).toBeVisible()

  await dialog.getByTestId('record-wrong').click()
  await expect(page.getByText('已加入错题本', { exact: true })).toBeVisible()

  const wrongState = await request.get(`${learner}/state`).then(response => response.json())
  const openMistakes = await request.get(`${learner}/mistakes?status=open`).then(response => response.json())
  expect(wrongState.student_id).toBe(student)
  expect(wrongState.revision).toBe(1)
  expect(openMistakes.items.some(item => item.question_id === questionId)).toBeTruthy()

  await dialog.getByTestId('record-correct').click()
  await expect(page.getByText('已记录为做对，相关错题已解决', { exact: true })).toBeVisible()

  const finalState = await request.get(`${learner}/state`).then(response => response.json())
  const resolvedMistakes = await request.get(`${learner}/mistakes?status=resolved`).then(response => response.json())
  expect(finalState.revision).toBe(2)
  expect(resolvedMistakes.items.some(item => item.question_id === questionId)).toBeTruthy()
})

test('assistant renders a graph question recommendation as a clickable link', async ({ page }) => {
  const student = `assistant_link_${Date.now()}`
  const detailUrl = `http://127.0.0.1:5173/questions?id=XY2111&student=${student}`

  await page.route('http://127.0.0.1:8600/api/chat', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      reply: `推荐这道题：${detailUrl}\n打开详情页后可标记做对或做错。`,
      tools: ['questions_of_knowledge'],
      profile: { nodes: [] }
    })
  }))
  await page.goto(`http://127.0.0.1:8600?student=${encodeURIComponent(student)}`)
  await page.locator('#msg').fill('给我推荐一道题目')
  await page.locator('#send').click()

  const recommendation = page.locator('.bubble.ai').last()
  const link = recommendation.locator('a')
  await expect(link).toHaveAttribute('href', detailUrl)
  await expect(link).toHaveAttribute('target', '_blank')
  await expect(recommendation).toContainText('可标记做对或做错')
})

test('question list filters by an exact Chinese question title', async ({ page }) => {
  await page.goto('/questions')
  await page.getByPlaceholder('搜索题目名称...').fill('小码哥的开心数字')

  const results = page.locator('.question-card')
  await expect(results).toHaveCount(1)
  await expect(results.first()).toContainText('MC0218')
  await expect(results.first()).toContainText('小码哥的开心数字')
  await expect(page.getByText('算法题目 (1 道)', { exact: true })).toBeVisible()
})

test('assistant restores the current student conversation after returning', async ({ page }) => {
  const student = `history_ui_${Date.now()}`
  const detailUrl = `http://127.0.0.1:5173/questions?id=MC0218&student=${student}`

  await page.route(/\/api\/chat\/history\?student=/, route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      student,
      items: [
        { role: 'user', content: '给我推荐一道题目' },
        {
          role: 'assistant',
          content: `推荐“小码哥的开心数字”：${detailUrl}`,
          tools: ['search_graph']
        }
      ]
    })
  }))

  await page.goto(`http://127.0.0.1:8600?student=${encodeURIComponent(student)}`)
  await expect(page.locator('.bubble.me')).toHaveText('给我推荐一道题目')
  await expect(page.locator('.bubble.ai')).toContainText('小码哥的开心数字')
  await expect(page.locator('.bubble.ai a')).toHaveAttribute('href', detailUrl)
  await expect(page.locator('.meta')).toContainText('search_graph')
})
