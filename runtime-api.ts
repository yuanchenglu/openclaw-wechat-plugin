/**
 * 微信服务号渠道运行时 API 导出
 * 
 * @description 导出插件所需的类型和运行时接口
 */

// ============================================
// 从 OpenClaw SDK 导入核心类型
// ============================================

export type {
  ChannelPlugin,
  OpenClawConfig,
  OpenClawPluginApi,
  PluginRuntime,
  OpenClawPluginService,
  OpenClawPluginServiceContext,
  PluginLogger,
} from "openclaw/plugin-sdk/core";

export type {
  ChannelOutboundContext,
  } from "openclaw/channels/plugins/types.adapters";
export type { OutboundDeliveryResult } from "openclaw/infra/outbound/deliver";

export {
  DEFAULT_ACCOUNT_ID,
  normalizeAccountId,
} from "openclaw/plugin-sdk/core";

// ============================================
// 类型定义（微信服务号特有）
// ============================================

/**
 * 微信服务号账户配置
 */
export interface WechatServiceConfig {
  /** 中转服务 WebSocket 地址 */
  relayUrl?: string;
  /** 本地 OpenClaw 服务地址 */
  openclawUrl?: string;
  /** 实例类型：local（本地裸机）或 cloud（云端 Docker） */
  instanceType?: "local" | "cloud";
  /** 允许发消息的用户 OpenID 列表 */
  allowFrom?: string[];
  /** 默认发送目标 */
  defaultTo?: string;
}

/**
 * 已解析的微信服务号账户
 */
export interface ResolvedWechatServiceAccount {
  /** 账户 ID */
  accountId: string;
  /** 账户名称 */
  name?: string;
  /** 是否启用 */
  enabled: boolean;
  /** 中转服务地址 */
  relayUrl?: string;
  /** 本地 OpenClaw 地址 */
  openclawUrl?: string;
  /** 实例类型 */
  instanceType?: "local" | "cloud";
  /** 原始配置 */
  config: WechatServiceConfig;
}

/**
 * WebSocket 连接状态
 */
export type ConnectionStatus =
  | "disconnected"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "error";