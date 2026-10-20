export type Role = "institution_admin" | "institution_staff" | "student";

export interface Me {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  institute_id: string;
  institution_name: string;
  institution_join_code: string | null;
}

export interface Job {
  id: string;
  job_type: string;
  status: "pending" | "processing" | "completed" | "failed";
  error: string | null;
  result: Record<string, unknown>;
}

export interface RoleSkill {
  id?: string;
  skill: string;
  required_level: number;
  importance_weight: number;
  topics: string[];
  question_categories: string[];
  source?: string;
  approval_status?: string;
  rationale?: string | null;
}

export interface InterviewStats {
  candidate_count: number;
  participated: number;
  in_progress: number;
  completed: number;
  average_score: number | null;
}

export interface Interview {
  id: string;
  name: string;
  target_role: string;
  job_description: string;
  duration_minutes: number;
  start_time: string | null;
  end_time: string | null;
  interview_type: "technical" | "behavioral" | "mixed";
  question_count: number;
  initial_difficulty: "easy" | "medium" | "hard";
  adaptive_mode: boolean;
  status: string;
  effective_status: string | null;
  skill_approval_state: string;
  eligibility_config: { mode: string; min_similarity: number };
  record_media: boolean;
  stats?: InterviewStats | null;
  skills?: RoleSkill[];
  created_at: string;
}

export interface CandidateInterview {
  id: string;
  name: string;
  target_role: string;
  interview_type: string;
  duration_minutes: number;
  question_count: number;
  start_time: string | null;
  end_time: string | null;
  status: string;
  joinable: boolean;
  eligibility_reason: string;
  participation_status: string;
  session_id: string | null;
}

export interface QuestionView {
  id: string;
  sequence: number;
  text: string;
  spoken_text: string | null;
  topic: string | null;
  difficulty: string;
  question_type: string;
  tts_url?: string | null;
}

/** What the server is doing with the answer to the current question. */
export interface TurnStatus {
  answer_id: string;
  status: string;
  phase: "transcribing" | "evaluating" | "choosing_next" | "evaluation_failed" | "failed" | "retrying" | string;
  attempts?: number;
  retry_allowed?: boolean;
  error?: string | null;
  message?: string;
}

export interface SessionState {
  session_id: string;
  interview_id: string;
  status: string;
  question_index: number;
  question_count: number;
  progress: number;
  current_topic: string | null;
  current_difficulty: string | null;
  started_at: string | null;
  duration_minutes: number;
  elapsed_seconds: number;
  current_question: QuestionView | null;
  awaiting: "answer" | "processing" | "none";
  turn?: TurnStatus | null;
  ice_servers: string[];
  record_media: boolean;
}

export interface WsEvent<T = Record<string, unknown>> {
  type: string;
  session_id?: string;
  ts?: string;
  data: T;
}

export interface Recommendation {
  area: string;
  area_type: string;
  recommendation: string;
  reason: string;
  priority?: number;
}

export interface ReportContent {
  overall_score: number | null;
  summary: string;
  final_assessment: string;
  criterion_scores: Record<string, number | null>;
  topic_performance: Record<string, { average: number | null; count: number }>;
  skill_performance: Record<string, { average: number | null; count: number }>;
  adaptive_progression: { sequence: number; difficulty: string; score: number; topic: string | null }[];
  strengths: string[];
  weaknesses: string[];
  missing_concepts: string[];
  weak_topics: string[];
  strong_topics: string[];
  readiness: {
    overall: number;
    level: string;
    components: Record<string, number | null>;
    disclaimer: string;
  };
  recommendations: Recommendation[];
  questions: { sequence: number; question: string; topic: string | null; difficulty: string; answer_excerpt: string;
    score: number | null; next_question_reason: string | null }[];
  interview: { name: string; target_role: string; type: string };
  candidate: { name: string };
  disclaimer: string;
  stop_reason: string | null;
}

export interface Report {
  id: string;
  session_id: string;
  version: number;
  content: ReportContent;
  export_status: string;
  download_url: string | null;
  created_at: string;
}

export interface QuestionDetail {
  id: string;
  sequence: number;
  text: string;
  topic: string | null;
  difficulty: string;
  question_type: string;
  reason: string | null;
  transcript: string | null;
  evaluation: null | {
    overall_score: number;
    band: string;
    confidence: number;
    criteria: Record<string, number>;
    strengths: { point: string; evidence: string | null }[];
    weaknesses: { point: string; evidence: string | null }[];
    missing_concepts: string[];
    improvement_actions: string[];
    suggested_answer_structure: string | null;
    practice_topics: string[];
    next_question_reason: string | null;
    evidence: { summary?: string };
  };
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  description: string | null;
  document_type: string;
  role: string | null;
  topic: string | null;
  status: string;
  current_version: number;
  created_at: string;
  updated_at: string;
  latest: null | { version: number; processing_status: string; indexing_status: string; chunk_count: number;
    error: string | null; embedding_model: string | null };
}
