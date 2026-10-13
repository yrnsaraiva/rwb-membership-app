// Edita aqui o texto de cada cena. Fotos: public/photos/01.jpg ... 08.jpg (9:16, 1080x1920 ou maior).
export const PROMPT = "Gemini, diz-me os factos mais interessantes sobre o RUNWITHBROTO.";

export type Fact = { kicker: string; title: string; body: string; photo: string; pos?: string };

export const FACTS: Fact[] = [
  {kicker: "FACTO 01", title: "Nasceu em\nMaputo.\nChegou à Matola.", body: "Da capital ao Parque dos Poetas: a comunidade cresceu e levou a corrida a novas ruas.", photo: "photos/02.jpg", pos: "52% 50%"},
  {kicker: "FACTO 02", title: "Ninguém fica\npara trás.", body: "We run together. We grow together. A consistência vence a motivação. E a rua é para todos.", photo: "photos/03.jpg"},
  {kicker: "FACTO 03", title: "Mais de 2 500\nmembros activos.", body: "Eventos chegam a ter mais de 1 000 inscrições numa única semana.", photo: "photos/04.jpg"},
  {kicker: "FACTO 04", title: "Setembro Amarelo:\n+1 000 a correr.", body: "Uma corrida pela saúde mental. Depois vieram o Outubro Rosa, o Novembro Azul e o Dezembro Vermelho.", photo: "photos/05.jpg"},
  {kicker: "FACTO 05", title: "25 de Junho,\nao amanhecer.", body: "No Dia da Independência, centenas de pessoas correm juntas, celebrando a liberdade em movimento.", photo: "photos/06.jpg"},
  {kicker: "FACTO 06", title: "Depois do 5 km,\nvem o café.", body: "As Coffee Parties juntam corrida descontraída, pequeno-almoço e convívio.", photo: "photos/07.jpg"},
];

export const OUTRO_PHOTO = "photos/08.jpg";
export const FPS = 30;
export const INTRO = 150;
export const FACT_LEN = 110;
export const OUTRO = 110;
export const TOTAL = INTRO + FACT_LEN * FACTS.length + OUTRO;
