import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "ANIMA",
  description: "ANIMA — the brain of an embodied robot",
};

// 首屏绘制前就把主题定好：读 localStorage 的偏好，没存过就用深色（默认）。
// 这样刷新带浅色偏好的页面时，不会先闪一下深色再变浅。
const THEME_INIT = `(function(){try{var t=localStorage.getItem('anima-theme');if(t!=='light'&&t!=='dark')t='dark';document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme='dark';}})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className="antialiased">{children}</body>
    </html>
  );
}
