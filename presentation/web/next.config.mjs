/** @type {import('next').NextConfig} */
const nextConfig = {
  // 关掉 Next 开发模式注入的 dev 工具指示器（默认在左下角那个会挡内容、又不能拖的「N」按钮）。
  // 只影响开发时的那个浮标，不动任何功能。左下角腾给我们自己的主题切换。
  devIndicators: false,
};

export default nextConfig;
