import { recordQuestionAttempt } from '@/stores/progress'

export function recordQuestionResult(questionId, knowledgePoints, correct) {
  void knowledgePoints
  return recordQuestionAttempt(questionId, { correct })
}
