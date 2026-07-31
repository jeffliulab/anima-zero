// /session-logs 独立路由：薄壳，渲染同款 SessionLogsView 组件（整页版）。
// 主界面里是内嵌版（embedded），逻辑同一份，见 components/SessionLogsView.tsx。
import LangToggle from "@/components/LangToggle";
import SessionLogsView from "@/components/SessionLogsView";

export default function SessionLogsPage() {
  return (
    <>
      {/* 整页路由没有侧栏，而语言切换器住在侧栏里——直接打开这个页面的人就没得换
          （ROADMAP R9）。在这里补一个浮在右上角的就够了。 */}
      <div className="fixed right-3 top-3 z-50">
        <LangToggle />
      </div>
      <SessionLogsView />
    </>
  );
}
