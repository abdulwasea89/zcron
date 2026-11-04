import type { ReactNode } from "react";
import { Manrope, Space_Grotesk } from "next/font/google";
import "./login.css";

const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope" });

const wordmark = Space_Grotesk({
  subsets: ["latin"],
  weight: "700",
  variable: "--font-wordmark",
});

export default function LoginLayout({ children }: { children: ReactNode }) {
  return <div className={`${manrope.variable} ${wordmark.variable}`}>{children}</div>;
}
