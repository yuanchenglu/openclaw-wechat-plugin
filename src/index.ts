/**
 * OpenClaw 微信频道插件 - 入口文件
 *
 * @version 2.0.0
 */

export {
  WechatChannelClient,
  type WechatChannelClientConfig,
  type WechatChannelClientCallbacks,
  type DeviceInfo,
  type ClientState,
  type InstanceType,
  type DeviceType,
  type WsMessage,
  type ChatRequestMessage,
  type ChatResponseMessage,
  type RegisterMessage,
  type RegisteredMessage,
  type StatusResponseMessage,
} from './websocket.js';

export { default } from './websocket.js';