/**
 * 微信服务号渠道共享定义
 * 
 * @description 定义渠道 ID、常量和元数据
 * @todo Task 5 将实现完整的配置适配器
 */

import type { ChannelPlugin, OpenClawConfig } from "openclaw/plugin-sdk/core";
import { DEFAULT_ACCOUNT_ID, normalizeAccountId } from "openclaw/plugin-sdk/core";
import type { ResolvedWechatServiceAccount, WechatServiceConfig } from "../runtime-api.js";

// ============================================
// 渠道常量定义
// ============================================

/** 渠道 ID */
export const WECHAT_SERVICE_CHANNEL = "wechat-service" as const;

// 重新导出 DEFAULT_ACCOUNT_ID 和 normalizeAccountId
export { DEFAULT_ACCOUNT_ID, normalizeAccountId };

// ============================================
// 账户管理函数
// ============================================

/**
 * 列出所有微信服务号账户 ID
 * @todo Task 5 实现完整的账户管理
 */
export function listWechatServiceAccountIds(cfg: OpenClawConfig): string[] {
  const accounts = cfg.channels?.[WECHAT_SERVICE_CHANNEL]?.accounts;
  if (!accounts) return [];
  return Object.keys(accounts);
}

/**
 * 解析微信服务号账户
 * @todo Task 5 实现完整的账户解析
 */
export function resolveWechatServiceAccount(params: {
  cfg: OpenClawConfig;
  accountId: string;
}): ResolvedWechatServiceAccount {
  const { cfg, accountId } = params;
  const normalizedId = normalizeAccountId(accountId);
  const accountConfig = cfg.channels?.[WECHAT_SERVICE_CHANNEL]?.accounts?.[normalizedId];
  const channelConfig = cfg.channels?.[WECHAT_SERVICE_CHANNEL];
  
  const config: WechatServiceConfig = {
    relayUrl: accountConfig?.relayUrl ?? channelConfig?.relayUrl,
    openclawUrl: accountConfig?.openclawUrl ?? channelConfig?.openclawUrl,
    instanceType: accountConfig?.instanceType ?? channelConfig?.instanceType,
    allowFrom: accountConfig?.allowFrom ?? channelConfig?.allowFrom,
    defaultTo: accountConfig?.defaultTo ?? channelConfig?.defaultTo,
  };
  
  return {
    accountId: normalizedId,
    name: accountConfig?.name,
    enabled: accountConfig?.enabled ?? true,
    relayUrl: config.relayUrl,
    openclawUrl: config.openclawUrl,
    instanceType: config.instanceType,
    config,
  };
}

// ============================================
// 插件基础配置（简化版本）
// ============================================

/**
 * 创建微信服务号插件基础配置
 * 
 * @param params.setupWizard - 设置向导配置
 * @param params.setup - 设置函数
 * @returns 插件基础配置
 * @todo Task 5 实现完整的插件基础
 */
export function createWechatServicePluginBase(params: {
  setupWizard: NonNullable<ChannelPlugin<ResolvedWechatServiceAccount>["setupWizard"]>;
  setup: NonNullable<ChannelPlugin<ResolvedWechatServiceAccount>["setup"]>;
}): Partial<ChannelPlugin<ResolvedWechatServiceAccount>> {
  return {
    id: WECHAT_SERVICE_CHANNEL,
    meta: {
      id: WECHAT_SERVICE_CHANNEL,
      label: "微信服务号",
      docsPath: "/channels/wechat-service",
      docsLabel: "wechat-service",
      blurb: "通过微信服务号与本地 OpenClaw 对话",
      selectionLabel: "微信服务号",
      detailLabel: "微信服务号",
      systemImage: "message",
      quickstartAllowFrom: true,
    },
    setupWizard: params.setupWizard,
    capabilities: {
      chatTypes: ["direct"],
      reactions: false,
      threads: false,
      media: true,
      polls: false,
      nativeCommands: false,
      blockStreaming: true,
    },
    setup: params.setup,
  };
}