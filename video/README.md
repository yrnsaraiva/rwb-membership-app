# RUNWITHBROTO · motion video (Remotion)

Vídeo vertical 1080x1920 · 30 fps · ~28 s: frame de "pergunta à IA" → 6 factos → fecho com logo.

```bash
cd video && npm install
npm run dev      # Remotion Studio (pré-visualização)
npm run build    # gera out/rwb-facts.mp4
```

## Fotos
Fotos em `public/photos/01…08.jpg` (já com as fotos reais do clube). Ordem: 01 abertura, 02–07 factos, 08 fecho.
`01.jpg` é o fundo da pergunta inicial; `08.jpg` o fundo do fecho; 02–07 são os 6 factos. Fotos do álbum Coffee Party:
https://coresvivasclientesmoz.pixieset.com/runwithbrotocoffeparty/

## Textos / duração
Tudo em `src/facts.ts` (pergunta, factos, duração das cenas). Animações em `src/RWBFacts.tsx`.
Marca: amarelo `#fabb00`, tinta `#0b0b0b`, Oswald + Inter (fontes locais em `public/fonts`).
