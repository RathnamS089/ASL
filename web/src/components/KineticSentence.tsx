import { motion, useReducedMotion } from "motion/react";
import { useMemo } from "react";
import { beats } from "../lib/kinetic";
import type { Translation } from "../lib/types";

/** The sentence, word by word, timed to the signs. `playKey` restarts the animation. */
export function KineticSentence({ translation, playKey, speed = 1, size = "xl" }: { translation: Translation; playKey: number; speed?: number; size?: "lg" | "xl" }) {
  const reduce = useReducedMotion();
  const words = useMemo(() => beats(translation, speed), [translation, speed]);
  const text = size === "xl" ? "text-[clamp(2.6rem,9vw,5.5rem)]" : "text-[clamp(2rem,6vw,3.2rem)]";

  return (
    <p className={`font-serif leading-[1.02] tracking-[-0.03em] ${text}`} aria-label={translation.sentence} role="text">
      {words.map((w, i) => {
        const tone =
          w.emphasis === "strong" ? "text-violet italic" : w.emphasis === "low_confidence" ? "text-paper/45 underline decoration-dotted decoration-violet/60 underline-offset-[0.15em]" : "text-paper";
        return (
          <motion.span
            key={`${playKey}-${i}`}
            aria-hidden="true"
            className={`mr-[0.22em] inline-block ${tone}`}
            title={w.sign ? `${w.sign}${w.confidence != null ? ` · ${Math.round(w.confidence * 100)}%` : ""}` : undefined}
            initial={reduce ? false : { opacity: 0, y: "0.45em", filter: "blur(10px)", rotate: -2 }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)", rotate: 0 }}
            transition={reduce ? { duration: 0 } : { delay: w.at, type: "spring", stiffness: 260, damping: 22, mass: 0.9 }}
          >
            {w.text}
          </motion.span>
        );
      })}
    </p>
  );
}
