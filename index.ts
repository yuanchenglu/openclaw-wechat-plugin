/**
 * OpenClaw 微信服务号渠道插件入口
 * 
 * @description 让用户通过微信服务号与本地 OpenClaw 对话
 * @version 2.0.0
 */

import { defineChannelPluginEntry } from "openclaw/plugin-sdk/core";
import { wechatServicePlugin } from "./src/channel.js";
import { setWechatServiceRuntime } from "./src/runtime.js";

// 导出插件实例
export { wechatServicePlugin } from "./src/channel.js";

// 导出运行时设置函数
export { setWechatServiceRuntime } from "./src/runtime.js";

// 默认导出：插件入口定义
export default defineChannelPluginEntry({
  id: "wechat-service",
  name: "微信服务号",
  description: "通过微信服务号与本地 OpenClaw 对话",
  plugin: wechatServicePlugin,
  setRuntime: setWechatServiceRuntime,
});