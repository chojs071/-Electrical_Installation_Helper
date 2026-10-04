/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_ANON_KEY?: string;
  readonly VITE_AI_API_KEY?: string;
  /** 구 이름 (하위 호환) */
  readonly VITE_NVIDIA_API_KEY?: string;
  readonly VITE_AI_BASE_URL?: string;
  readonly VITE_AI_MODEL?: string;
  /** 이미지 설명 전담 모델 (미지정 시 VITE_AI_MODEL과 동일) */
  readonly VITE_VISION_MODEL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
