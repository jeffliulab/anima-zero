"use client";

import { useI18n } from "@/lib/i18n";

/** 侧栏底部的中/英切换,和主题按钮并排。
 *  显示的是**当前语言**(中/EN),点一下切到另一个并记住偏好——和主题按钮同一套语汇。 */
export default function LangToggle() {
  const { lang, setLang, t } = useI18n();
  const isEn = lang === "en";
  return (
    <button
      onClick={() => setLang(isEn ? "zh" : "en")}
      title={isEn ? t("切换到中文界面") : t("切换到英文界面")}
      aria-label={t("界面语言")}
      className="flex h-7 w-7 items-center justify-center rounded-md border border-neutral-700 text-[11px] font-medium text-neutral-400 transition-colors hover:border-neutral-500 hover:text-neutral-100"
    >
      {isEn ? "EN" : "中"}
    </button>
  );
}
