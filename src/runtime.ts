/**
 * 微信服务号运行时配置
 * 
 * @description 提供运行时依赖注入和配置管理
 */

import type { PluginRuntime } from "openclaw/plugin-sdk/core";
import type { WechatChannelClient } from "./websocket.js";

// ============================================
// 运行时实例存储
// ============================================

let _runtime: PluginRuntime | null = null;

/**
 * 设置微信服务号运行时
 * 
 * @param runtime - 插件运行时实例
 */
export function setWechatServiceRuntime(runtime: PluginRuntime): void {
  _runtime = runtime;
}

/**
 * 获取微信服务号运行时
 * 
 * @returns 运行时实例，如果未设置则抛出错误
 */
export function getWechatServiceRuntime(): PluginRuntime {
  if (!_runtime) {
    throw new Error("微信服务号运行时未初始化，请先调用 setWechatServiceRuntime");
  }
  return _runtime;
}

/**
 * 检查运行时是否已初始化
 */
export function isWechatServiceRuntimeInitialized(): boolean {
  return _runtime !== null;
}

// ============================================
// WebSocket 客户端管理
// ============================================

/**
 * WebSocket 客户端存储
 * 
 * @description 按 accountId 存储客户端实例，支持多账户
 */
const _clients: Map<string, WechatChannelClient> = new Map();

/**
 * 设置 WebSocket 客户端
 * 
 * @param accountId - 账户 ID
 * @param client - WebSocket 客户端实例
 */
export function setWechatChannelClient(accountId: string, client: WechatChannelClient): void {
  _clients.set(accountId, client);
}

/**
 * 获取 WebSocket 客户端
 * 
 * @param accountId - 账户 ID（可选，默认为 "default"）
 * @returns WebSocket 客户端实例，如果不存在返回 undefined
 */
export function getWechatChannelClient(accountId?: string): WechatChannelClient | undefined {
  return _clients.get(accountId ?? "default");
}

/**
 * 删除 WebSocket 客户端
 * 
 * @param accountId - 账户 ID
 */
export function deleteWechatChannelClient(accountId: string): void {
  _clients.delete(accountId);
}

/**
 * 检查客户端是否已连接
 * 
 * @param accountId - 账户 ID（可选，默认为 "default"）
 */
export function isWechatChannelClientConnected(accountId?: string): boolean {
  const client = getWechatChannelClient(accountId);
  return client?.getState().connected ?? false;
}