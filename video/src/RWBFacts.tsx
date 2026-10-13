import React from "react";
import {continueRender, delayRender, AbsoluteFill, Img, Sequence, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig, Easing} from "remotion";
import {FACTS, FACT_LEN, INTRO, OUTRO, OUTRO_PHOTO, PROMPT} from "./facts";

// Fontes locais (public/fonts), para o render não depender da rede.
const OSWALD = "RWB Oswald";
const INTER = "RWB Inter";
const fontFaces = [
  ["RWB Oswald", 500, "oswald-latin-500-normal"], ["RWB Oswald", 700, "oswald-latin-700-normal"],
  ["RWB Inter", 500, "inter-latin-500-normal"], ["RWB Inter", 600, "inter-latin-600-normal"],
] as const;
if (typeof document !== "undefined") {
  fontFaces.forEach(([family, weight, file]) => {
    const handle = delayRender(`font ${file}`);
    new FontFace(family, `url(${staticFile(`fonts/${file}.woff2`)})`, {weight: String(weight)})
      .load().then((ff) => { document.fonts.add(ff); continueRender(handle); }).catch((e) => { console.error(e); continueRender(handle); });
  });
}

const BRAND = "#fabb00";
const INK = "#0b0b0b";
const clamp = {extrapolateLeft: "clamp", extrapolateRight: "clamp"} as const;

const Photo: React.FC<{src: string; dark?: number; len: number; dir?: 1 | -1; pos?: string}> = ({src, dark = 0.45, len, dir = 1, pos = "50% 50%"}) => {
  const f = useCurrentFrame();
  const scale = interpolate(f, [0, len], dir === 1 ? [1.08, 1.24] : [1.24, 1.08], clamp);
  const x = interpolate(f, [0, len], [0, -40 * dir], clamp);
  return (
    <AbsoluteFill style={{background: INK}}>
      <AbsoluteFill style={{transform: `translateX(${x}px) scale(${scale})`}}>
        <Img src={staticFile(src)} style={{width: "100%", height: "100%", objectFit: "cover", objectPosition: pos}} />
      </AbsoluteFill>
      <AbsoluteFill style={{background: `linear-gradient(180deg, rgba(11,11,11,${dark}) 0%, rgba(11,11,11,${dark * 0.4}) 40%, rgba(11,11,11,${dark + 0.4}) 100%)`}} />
    </AbsoluteFill>
  );
};

const Rain: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{pointerEvents: "none"}}>
      {new Array(90).fill(0).map((_, i) => {
        const speed = 10 + random(`s${i}`) * 18;
        const y = ((random(`y${i}`) * 2200 + f * speed) % 2200) - 140;
        const x = random(`x${i}`) * 1080 - f * 1.5;
        const h = 14 + random(`h${i}`) * 36;
        return <div key={i} style={{position: "absolute", left: x, top: y, width: 2.5, height: h, borderRadius: 2, background: "rgba(255,255,255,0.35)", transform: "rotate(6deg)"}} />;
      })}
    </AbsoluteFill>
  );
};

const Sparkle: React.FC<{size: number; spin: number}> = ({size, spin}) => (
  <svg width={size} height={size} viewBox="0 0 100 100" style={{transform: `rotate(${spin}deg)`}}>
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#ff5a4d" /><stop offset=".5" stopColor={BRAND} /><stop offset="1" stopColor="#3b82f6" />
      </linearGradient>
    </defs>
    <path d="M50 0 C54 30 70 46 100 50 C70 54 54 70 50 100 C46 70 30 54 0 50 C30 46 46 30 50 0Z" fill="url(#g)" />
  </svg>
);

const Intro: React.FC = () => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame: f, fps, config: {damping: 14, stiffness: 110}});
  const typed = Math.floor(interpolate(f, [22, 100], [0, PROMPT.length], clamp));
  const text = PROMPT.slice(0, typed);
  const sendPulse = f > 108 ? 1 + 0.12 * Math.sin((f - 108) * 0.5) : 1;
  const pressed = f > 124;
  const fadeOut = interpolate(f, [INTRO - 14, INTRO], [1, 0], clamp);
  const cursorOn = Math.floor(f / 12) % 2 === 0 && typed < PROMPT.length;
  // "Gemini," em negrito, resto normal, e destaque do RUNWITHBROTO
  const render = (t: string) => {
    const parts = t.split(/(Gemini,|factos mais interessantes|RUNWITHBROTO)/);
    return parts.map((p, i) =>
      p === "Gemini," || p === "factos mais interessantes" || p === "RUNWITHBROTO"
        ? <b key={i} style={{fontWeight: 700, color: p === "RUNWITHBROTO" ? BRAND : "#fff"}}>{p}</b>
        : <span key={i}>{p}</span>);
  };
  return (
    <AbsoluteFill style={{opacity: fadeOut}}>
      <Photo src="photos/01.jpg" len={INTRO} dark={0.55} />
      <Rain />
      <div style={{position: "absolute", left: 60, right: 60, top: 190, transform: `translateY(${(1 - enter) * -120}px) scale(${0.92 + enter * 0.08})`, opacity: enter}}>
        <div style={{background: "rgba(11,11,11,0.94)", borderRadius: 80, padding: "64px 64px 52px", boxShadow: `0 0 0 3px rgba(255,255,255,0.18), 0 0 90px rgba(250,187,0,${pressed ? 0.15 : 0.35})`, minHeight: 440, position: "relative"}}>
          <div style={{fontFamily: INTER, fontWeight: 500, fontSize: 64, lineHeight: 1.25, color: "#e8e8e8", minHeight: 240}}>
            {render(text)}
            {cursorOn && <span style={{display: "inline-block", width: 5, height: 64, background: BRAND, marginLeft: 6, verticalAlign: "middle"}} />}
          </div>
          <div style={{display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 30}}>
            <Sparkle size={78} spin={f * 1.6} />
            <div style={{width: 104, height: 104, borderRadius: 52, background: BRAND, display: "grid", placeItems: "center", transform: `scale(${pressed ? 0.88 : sendPulse})`, boxShadow: `0 0 0 ${pressed ? 0 : 10}px rgba(250,187,0,0.25)`}}>
              <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke={INK} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
            </div>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const FactScene: React.FC<{i: number}> = ({i}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const fact = FACTS[i];
  const fadeIn = interpolate(f, [0, 8], [0, 1], clamp);
  const fadeOut = interpolate(f, [FACT_LEN - 8, FACT_LEN], [1, 0], clamp);
  const lines = fact.title.split("\n");
  const kick = spring({frame: f - 4, fps, config: {damping: 16}});
  const bar = interpolate(f, [6, 26], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  const body = interpolate(f, [34, 52], [0, 1], clamp);
  return (
    <AbsoluteFill style={{opacity: fadeIn * fadeOut}}>
      <Photo src={fact.photo} len={FACT_LEN} dir={i % 2 === 0 ? 1 : -1} dark={0.4} pos={fact.pos} />
      <AbsoluteFill style={{justifyContent: "flex-end", padding: "0 70px 230px"}}>
        <div style={{display: "inline-flex", alignSelf: "flex-start", background: BRAND, color: INK, fontFamily: OSWALD, fontWeight: 700, fontSize: 44, letterSpacing: 6, padding: "10px 28px", borderRadius: 10, opacity: kick, transform: `translateY(${(1 - kick) * 30}px)`}}>
          {fact.kicker}
        </div>
        <div style={{height: 10, width: `${bar * 100}%`, maxWidth: 220, background: BRAND, margin: "28px 0 30px"}} />
        {lines.map((l, k) => {
          const p = spring({frame: f - 12 - k * 7, fps, config: {damping: 15, stiffness: 120}});
          return (
            <div key={k} style={{overflow: "hidden"}}>
              <div style={{fontFamily: OSWALD, fontWeight: 700, fontSize: 112, lineHeight: 1.0, color: "#fff", textTransform: "uppercase", transform: `translateY(${(1 - p) * 150}px)`, opacity: p}}>{l}</div>
            </div>
          );
        })}
        <div style={{fontFamily: INTER, fontWeight: 500, fontSize: 48, lineHeight: 1.35, color: "#e8e8e8", marginTop: 34, opacity: body, transform: `translateY(${(1 - body) * 24}px)`, maxWidth: 900}}>{fact.body}</div>
      </AbsoluteFill>
      <div style={{position: "absolute", top: 80, left: 70, right: 70, display: "flex", justifyContent: "space-between", alignItems: "center"}}>
        <Img src={staticFile("wordmark-yellow.png")} style={{height: 64}} />
        <div style={{fontFamily: OSWALD, color: "#fff", fontSize: 36, letterSpacing: 4}}>{i + 1} / {FACTS.length}</div>
      </div>
    </AbsoluteFill>
  );
};

const Outro: React.FC = () => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const fadeIn = interpolate(f, [0, 10], [0, 1], clamp);
  const logo = spring({frame: f - 6, fps, config: {damping: 12, stiffness: 100}});
  const t1 = spring({frame: f - 26, fps, config: {damping: 15}});
  const t2 = interpolate(f, [48, 66], [0, 1], clamp);
  return (
    <AbsoluteFill style={{opacity: fadeIn}}>
      <Photo src={OUTRO_PHOTO} len={OUTRO} dark={0.62} />
      <AbsoluteFill style={{alignItems: "center", justifyContent: "center", textAlign: "center", padding: 70}}>
        <Img src={staticFile("logo-yellow.png")} style={{width: 760, transform: `scale(${0.6 + logo * 0.4})`, opacity: logo}} />
        <div style={{fontFamily: OSWALD, fontWeight: 700, fontSize: 124, lineHeight: 1.02, color: "#fff", textTransform: "uppercase", marginTop: 60, opacity: t1, transform: `translateY(${(1 - t1) * 60}px)`}}>
          Junta-te<br /><span style={{color: BRAND}}>ao clube</span>
        </div>
        <div style={{fontFamily: INTER, fontWeight: 600, fontSize: 44, color: "#e8e8e8", marginTop: 44, opacity: t2}}>Corre. Convive. Repete.</div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const RWBFacts: React.FC = () => (
  <AbsoluteFill style={{background: INK}}>
    <Sequence from={0} durationInFrames={INTRO}><Intro /></Sequence>
    {FACTS.map((_, i) => (
      <Sequence key={i} from={INTRO + i * FACT_LEN} durationInFrames={FACT_LEN}><FactScene i={i} /></Sequence>
    ))}
    <Sequence from={INTRO + FACTS.length * FACT_LEN} durationInFrames={OUTRO}><Outro /></Sequence>
  </AbsoluteFill>
);
