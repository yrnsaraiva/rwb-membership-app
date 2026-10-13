// Edita aqui o texto de cada cena. Fotos: public/photos/01.jpg ... 06.jpg (9:16, 1080x1920 ou maior).
export const PROMPT = "Gemini, diz-me os factos mais interessantes sobre o RUNWITHBROTO.";

export type Fact = { kicker: string; title: string; body: string; photo: string };

export const FACTS: Fact[] = [
  {kicker: "FACTO 01", title: "Corremos juntos.\nE o café\nvem depois.", body: "A Coffee Party é a prova de que o melhor pace é o da conversa.", photo: "photos/01.jpg"},
  {kicker: "FACTO 02", title: "Cada corrida\nvale pontos.", body: "Regista as tuas corridas na app e vê os pontos a crescer.", photo: "photos/02.jpg"},
  {kicker: "FACTO 03", title: "Streaks:\nquem não falha,\nsobe.", body: "Semana após semana, a consistência é o que te põe à frente.", photo: "photos/03.jpg"},
  {kicker: "FACTO 04", title: "Ranking mensal\ne geral.", body: "Quem lidera este mês? Quem lidera de sempre? Está tudo à vista.", photo: "photos/04.jpg"},
  {kicker: "FACTO 05", title: "O teu cartão\nvive no\ntelemóvel.", body: "Um QR e entras no evento. Presença e pontos ficam registados.", photo: "photos/05.jpg"},
];

export const OUTRO_PHOTO = "photos/06.jpg";
export const FPS = 30;
export const INTRO = 150;
export const FACT_LEN = 100;
export const OUTRO = 110;
export const TOTAL = INTRO + FACT_LEN * FACTS.length + OUTRO;
