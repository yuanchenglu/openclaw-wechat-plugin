/**
 * 微信服务号渠道插件实现
 * 
 * @description 完整的渠道插件，支持 Block Streaming
 */

import { attachChannelToResult } from "openclaw/plugin-sdk/channel-send-result";
import { createTopLevelChannelConfigAdapter } from "openclaw/plugin-sdk/channel-config-helpers";
import { createChatChannelPlugin } from "openclaw/plugin-sdk/core";
import type { ChannelOutboundContext, OutboundDeliveryResult, ResolvedWechatServiceAccount } from "../runtime-api.js";
import {
  WECHAT_SERVICE_CHANNEL,
  DEFAULT_ACCOUNT_ID,
  normalizeAccountId,
  listWechatServiceAccountIds,
  resolveWechatServiceAccount,
} from "./shared.js";
import {
  getWechatChannelClient,
  setWechatChannelClient,
  deleteWechatChannelClient,
} from "./runtime.js";
import { WechatChannelClient, type DeviceInfo } from "./websocket.js";

// ============================================
// 配置适配器
// ============================================

const wechatServiceConfigAdapter = createTopLevelChannelConfigAdapter<ResolvedWechatServiceAccount>({
  sectionKey: WECHAT_SERVICE_CHANNEL,
  resolveAccount: (cfg) => resolveWechatServiceAccount({ cfg, accountId: DEFAULT_ACCOUNT_ID }),
  listAccountIds: listWechatServiceAccountIds,
  defaultAccountId: () => DEFAULT_ACCOUNT_ID,
  deleteMode: "clear-fields",
  clearBaseFields: ["name", "relayUrl", "openclawUrl", "instanceType", "allowFrom", "defaultTo"],
  resolveAllowFrom: (account) => account.config.allowFrom,
  formatAllowFrom: (allowFrom) =>
    allowFrom
      .map((entry) => String(entry).trim())
      .filter(Boolean),
});

// ============================================
// 辅助函数
// ============================================

/**
 * 发送文本消息到微信用户
 * 
 * @param params - 发送参数
 * @returns 发送结果
 */
async function sendWechatText(params: ChannelOutboundContext): Promise<Omit<OutboundDeliveryResult, "channel">> {
  const { to, text, accountId } = params;
  
  // 获取对应的客户端实例
  const aid = normalizeAccountId(accountId);
  const client = getWechatChannelClient(aid);
  
  if (!client) {
    // 返回空的 messageId 表示发送失败
    return { messageId: "" };
  }
  
  const state = client.getState();
  if (!state.connected) {
    // 返回空的 messageId 表示发送失败
    return { messageId: "" };
  }
  
  try {
    // 通过 WebSocket 发送消息给中转服务
    // to 是用户的 openid
    await client.sendChatResponse(to, text);
    
    return {
      messageId: `wechat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    };
  } catch {
    // 返回空的 messageId 表示发送失败
    return { messageId: "" };
  }
}

// ============================================
// 插件实现
// ============================================

/**
 * 微信服务号渠道插件
 * 
 * 此插件允许用户通过微信服务号与本地 OpenClaw 对话。
 * 架构：微信服务号 <-> 中转服务 <-> 本地客户端 <-> OpenClaw
 */
export const wechatServicePlugin = createChatChannelPlugin<ResolvedWechatServiceAccount>({
  base: {
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
    capabilities: {
      chatTypes: ["direct"],
      reactions: false,
      threads: false,
      media: true,
      polls: false,
      nativeCommands: false,
      blockStreaming: true,  // 支持 Block Streaming
    },
    
    config: {
      ...wechatServiceConfigAdapter,
      isConfigured: (account) => Boolean(account.relayUrl?.trim()),
      unconfiguredReason: (account) => {
        if (!account.relayUrl?.trim()) return "未配置中转服务地址";
        return "未配置";
      },
    },
    
    gateway: {
      startAccount: async (ctx) => {
        const account = ctx.account;
        ctx.log?.info(`[${account.accountId}] 微信服务号插件启动`);
        
        // 检查是否已配置
        if (!account.relayUrl?.trim()) {
          throw new Error("未配置中转服务地址");
        }
        
        // 创建 WebSocket 客户端
        const client = new WechatChannelClient(
          {
            relayUrl: account.relayUrl,
            instanceType: account.instanceType ?? "local",
          },
          {
            onChatRequest: async (message) => {
              // 调用本地 OpenClaw API 处理消息
              // 这里由 OpenClaw 核心处理，我们只返回占位符
              // 实际的消息处理在 OpenClaw 核心中完成
              return message.content;
            },
            onConnect: () => {
              ctx.log?.info(`[${account.accountId}] WebSocket 已连接`);
            },
            onDisconnect: () => {
              ctx.log?.warn?.(`[${account.accountId}] WebSocket 已断开`);
            },
            onAuthorized: (openid) => {
              ctx.log?.info(`[${account.accountId}] 已授权，openid: ${openid}`);
            },
            onError: (error) => {
              ctx.log?.error?.(`[${account.accountId}] WebSocket 错误: ${error.message}`);
            },
            onAuthRequired: (authUrl) => {
              ctx.log?.info(`[${account.accountId}] 需要授权: ${authUrl}`);
            },
            onReconnecting: (attempt, delay) => {
              ctx.log?.debug?.(`[${account.accountId}] 重连中 (第 ${attempt} 次，${delay}ms 后重试)`);
            },
          }
        );
        
        // 存储客户端实例
        setWechatChannelClient(account.accountId, client);
        
        // 连接到中转服务
        const deviceInfo: DeviceInfo = {
          deviceId: account.accountId,
          deviceType: account.instanceType === "cloud" ? "docker_cloud" : "bare",
          machineId: "",
          systemUsername: "",
          isNewDevice: false,
        };
        
        await client.connect(deviceInfo);
        
        ctx.log?.info(`[${account.accountId}] 微信服务号插件已启动`);
        
        // 返回清理函数
        return {
          stop: async () => {
            await client.disconnect();
            deleteWechatChannelClient(account.accountId);
            ctx.log?.info(`[${account.accountId}] 微信服务号插件已停止`);
          },
        };
      },
      logoutAccount: async () => ({
        cleared: false,
        envToken: false,
        loggedOut: true,
      }),
    },
  },
  
  security: {
    dm: {
      channelKey: WECHAT_SERVICE_CHANNEL,
      resolvePolicy: () => "allow-configured" as const,
      resolveAllowFrom: (account: { config?: { allowFrom?: string[] } }) => 
        account.config?.allowFrom,
      policyPathSuffix: "dmPolicy",
      normalizeEntry: (raw: string) => raw.replace(/^(wechat|wx):/i, ""),
    },
    collectWarnings: () => [],
  },
  
  outbound: {
    base: {
      deliveryMode: "direct" as const,
      textChunkLimit: 2000,
    },
    attachedResults: {
      channel: WECHAT_SERVICE_CHANNEL,
      sendText: async (ctx: ChannelOutboundContext) => {
        const result = await sendWechatText(ctx);
        return result;
      },
    },
  },
});

export default wechatServicePlugin;