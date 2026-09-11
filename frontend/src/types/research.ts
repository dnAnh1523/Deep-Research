export interface Citation {
  id: number;
  number: number;
  doc_id?: string;
  title: string;
  authors?: string;
  publisher: string;
  year: number;
  url: string;
  snippet: string;
  all_snippets?: string[];
  verified: boolean;
  type?: string;
}

export interface SectionNode {
  id: string;
  title: string;
  level: 2 | 3;
}

export interface ResearchPlan {
  title: string;
  steps: string[];
  time_estimate: string;
  full_explanation?: string;
  status?: 'pending' | 'started' | 'editing';
}

export interface ThoughtStep {
  id: string;
  title: string;
  detail: string;
}

export interface WebSourceChip {
  url: string;
  title: string;
  domain: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text?: string;
  type?: 'text' | 'plan' | 'plan_edit_request' | 'start_confirmation' | 'completed_notice';
  plan?: ResearchPlan;
  timestamp?: string;
}

export interface ResearchSession {
  id: string;
  title: string;
  date: string;
  messages: ChatMessage[];
  plan?: ResearchPlan;
  report?: string;
  citations?: Record<number, Citation>;
  thoughtSteps?: ThoughtStep[];
  webSources?: WebSourceChip[];
  status: 'idle' | 'planning' | 'editing_plan' | 'researching' | 'completed' | 'error';
}
