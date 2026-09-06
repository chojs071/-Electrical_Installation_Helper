// Cloudflare Pages Function: POST /api/ai/chat/completions
// 브라우저 → (same-origin) → 본 함수 → upstream AI API.
// API 키는 서버 시크릿(NVIDIA_API_KEY)으로만 보관되어 클라이언트에 노출되지 않습니다.

interface PagesEnv {
  NVIDIA_API_KEY?: string;
  AI_BASE_URL?: string;
  AI_MODEL?: string;
}

interface PagesContext {
  request: Request;
  env: PagesEnv;
}

const UPSTREAM_DEFAULT = "https://ollama.com/v1";
const FALLBACK_MODEL = "gemma4:31b-cloud";
const MISSING_KEY_MESSAGE =
  "AI API 키가 서버에 설정되지 않았습니다. Cloudflare Pages 대시보드 > Settings > Environment variables에서 NVIDIA_API_KEY를 Secret으로 등록하세요.";

export async function onRequestPost(context: PagesContext): Promise<Response> {
  const { request, env } = context;

  const headerAuth = request.headers.get("authorization");
  const clientKey =
    headerAuth && headerAuth.startsWith("Bearer ") ? headerAuth.slice(7).trim() : "";
  // 서버 시크릿 우선, 없으면 로컬 dev용 클라이언트 키 허용
  const apiKey = env.NVIDIA_API_KEY || clientKey;
  if (!apiKey) {
    return Response.json({ error: MISSING_KEY_MESSAGE }, { status: 500 });
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "잘못된 JSON 요청입니다." }, { status: 400 });
  }
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    return Response.json({ error: "잘못된 JSON 요청입니다." }, { status: 400 });
  }
  const body: Record<string, unknown> = { ...(payload as Record<string, unknown>) };
  if (typeof body.model !== "string" || !body.model) {
    body.model = env.AI_MODEL || FALLBACK_MODEL;
  }

  const base = (env.AI_BASE_URL || UPSTREAM_DEFAULT).replace(/\/+$/, "");
  let upstream: Response;
  try {
    upstream = await fetch(`${base}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify(body),
    });
  } catch (e) {
    return Response.json(
      { error: `AI 서버 연결 실패: ${e instanceof Error ? e.message : String(e)}` },
      { status: 502 }
    );
  }

  // SSE 스트리밍 그대로 전달
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "text/event-stream",
      "cache-control": "no-cache",
      "x-accel-buffering": "no",
    },
  });
}

export async function onRequestOptions(): Promise<Response> {
  return new Response(null, {
    status: 204,
    headers: {
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "POST, OPTIONS",
      "access-control-allow-headers": "content-type, authorization",
      "access-control-max-age": "86400",
    },
  });
}
