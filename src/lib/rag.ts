import { RAG_MAX_CHARS, RAG_MAX_FILES } from "./constants";

// 빌드 타임에 data/ 폴더의 규정 텍스트 파일을 번들에 포함 (pdf_data 등 하위 폴더 제외)
const rawFiles = import.meta.glob("/data/*.{txt,md,json,csv}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const FILES = Object.entries(rawFiles).map(([filePath, content]) => ({
  filename: filePath.split("/").pop() ?? filePath,
  content,
}));

export function hasReferenceData(): boolean {
  return FILES.length > 0;
}

/**
 * 사용자 질문과 관련된 파일만 선별하여 최대 용량만큼만 반환
 * (원본 app.py load_relevant_data 와 동일 로직: 키워드 점수 상위 2개 × 2000자)
 */
export function loadRelevantData(
  prompt: string,
  maxFiles: number = RAG_MAX_FILES,
  maxCharsPerFile: number = RAG_MAX_CHARS
): string {
  const cleaned = prompt
    .toLowerCase()
    .split("알려줘")
    .join("")
    .split("해주세요")
    .join("")
    .split("설명해줘")
    .join("");
  const promptKeywords = [...new Set(cleaned.split(/\s+/).filter(Boolean))];

  const scoredFiles = FILES.map((file) => {
    const contentLower = file.content.toLowerCase();
    const score = promptKeywords.reduce(
      (acc, kw) => acc + (kw.length > 1 && contentLower.includes(kw) ? 1 : 0),
      0
    );
    return { ...file, score };
  }).sort((a, b) => b.score - a.score);

  const contextTexts: string[] = [];
  for (const { filename, content } of scoredFiles.slice(0, maxFiles)) {
    const truncated =
      content.length > maxCharsPerFile
        ? content.slice(0, maxCharsPerFile) + "\n...(이하 내용 생략)..."
        : content;
    contextTexts.push(`--- [참고 파일명: ${filename}] ---\n${truncated}\n`);
  }

  if (contextTexts.length === 0 && scoredFiles.length > 0) {
    const { filename, content } = scoredFiles[0];
    contextTexts.push(
      `--- [참고 파일명: ${filename} (전체 파일 중 일부)] ---\n${content.slice(0, RAG_MAX_CHARS)}...\n`
    );
  }

  return contextTexts.join("\n");
}
