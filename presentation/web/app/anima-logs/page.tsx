// /anima-logs 独立路由：薄壳，渲染同款 AnimaLogsView 组件（整页版）。
// 主界面里是内嵌版（embedded），逻辑同一份，见 components/AnimaLogsView.tsx。
import AnimaLogsView from "@/components/AnimaLogsView";

export default function AnimaLogsPage() {
  return <AnimaLogsView />;
}
