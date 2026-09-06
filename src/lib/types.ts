export type Role = "user" | "assistant" | "system";

export interface TextPart {
  type: "text";
  text: string;
}

export interface ImagePart {
  type: "image_url";
  image_url: { url: string };
}

export type MessageContent = string | Array<TextPart | ImagePart>;

export interface ChatMessage {
  role: Role;
  content: MessageContent;
}

export interface Chat {
  id: string;
  title: string;
  messages: ChatMessage[];
}

export interface SessionUser {
  id: string;
  displayUserId: string;
}
