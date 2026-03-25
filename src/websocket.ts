/**
 * OpenClaw 微信频道插件 - WebSocket 客户端模块
 *
 * 功能：
 * 1. 连接中转服务的 WebSocket
 * 2. 处理 chat_request 入站消息
 * 3. 发送 chat_response 出站消息
 * 4. 心跳机制
 * 5. 自动重连
 *
 * @version 2.0.0
 */

import WebSocket from 'ws';

// ==================== 类型定义 ====================

/**
 * 实例类型
 */
export type InstanceType = 'local' | 'cloud';

/**
 * 设备类型
 */
export type DeviceType = 'bare' | 'ecs' | 'docker_local' | 'docker_cloud';

/**
 * WebSocket 消息类型
 */
export type WsMessageType =
  | 'register'
  | 'registered'
  | 'chat_request'
  | 'chat_response'
  | 'ping'
  | 'pong'
  | 'status'
  | 'status_response'
  | 'error'
  | 'update_required';

/**
 * WebSocket 消息接口
 */
export interface WsMessage {
  type: WsMessageType;
  id?: string;
  device_id?: string;
  openid?: string;
  content?: string;
  msg_type?: string;
  error?: string;
  client_version?: string;
  [key: string]: unknown;
}

/**
 * 注册消息
 */
export interface RegisterMessage extends WsMessage {
  type: 'register';
  instance_type: InstanceType;
  device_id: string;
  device_type: DeviceType;
  machine_id: string;
  system_username: string;
  client_version: string;
  min_server_version: string;
  is_new_device: boolean;
}

/**
 * 注册响应消息
 */
export interface RegisteredMessage extends WsMessage {
  type: 'registered';
  server_version: string;
  auth_url: string;
  is_recovery: boolean;
  recovered_openid?: string;
  version_compatible: boolean;
  recommended_client_version?: string;
}

/**
 * 聊天请求消息（入站）
 */
export interface ChatRequestMessage extends WsMessage {
  type: 'chat_request';
  openid: string;
  content: string;
  msg_type: string;
  session_key?: string;
}

/**
 * 聊天响应消息（出站）
 */
export interface ChatResponseMessage extends WsMessage {
  type: 'chat_response';
  openid: string;
  content: string;
  client_version: string;
}

/**
 * 状态响应消息
 */
export interface StatusResponseMessage extends WsMessage {
  type: 'status_response';
  is_authorized: boolean;
  openid?: string;
}

/**
 * 客户端配置
 */
export interface WechatChannelClientConfig {
  /** 中转服务 WebSocket 地址 */
  relayUrl?: string;
  /** 实例类型：local（本地）或 cloud（云端） */
  instanceType?: InstanceType;
  /** 客户端版本 */
  clientVersion?: string;
  /** 最低服务端版本 */
  minServerVersion?: string;
  /** 心跳间隔（毫秒），默认 30000 */
  heartbeatInterval?: number;
  /** 初始重连延迟（毫秒），默认 1000 */
  initialRetryDelay?: number;
  /** 最大重连延迟（毫秒），默认 30000 */
  maxRetryDelay?: number;
  /** 连接超时（毫秒），默认 10000 */
  connectionTimeout?: number;
  /** WebSocket ping 间隔（毫秒），默认 30000 */
  pingInterval?: number;
  /** WebSocket ping 超时（毫秒），默认 10000 */
  pingTimeout?: number;
}

/**
 * 设备信息
 */
export interface DeviceInfo {
  deviceId: string;
  deviceType: DeviceType;
  machineId: string;
  systemUsername: string;
  isNewDevice: boolean;
}

/**
 * 客户端状态
 */
export interface ClientState {
  connected: boolean;
  authorized: boolean;
  deviceId: string | null;
  openid: string | null;
  serverVersion: string | null;
}

/**
 * 事件回调类型
 */
export interface WechatChannelClientCallbacks {
  /** 收到聊天请求时调用 */
  onChatRequest: (message: ChatRequestMessage) => Promise<string> | string;
  /** 连接成功时调用 */
  onConnect?: () => void;
  /** 断开连接时调用 */
  onDisconnect?: () => void;
  /** 授权成功时调用 */
  onAuthorized?: (openid: string) => void;
  /** 发生错误时调用 */
  onError?: (error: Error) => void;
  /** 需要授权时调用（返回授权链接） */
  onAuthRequired?: (authUrl: string) => void;
  /** 重连时调用 */
  onReconnecting?: (attempt: number, delay: number) => void;
}

// ==================== 常量 ====================

const DEFAULT_CONFIG: Required<Omit<WechatChannelClientConfig, 'deviceId'>> = {
  relayUrl: 'wss://claw.7color.vip/ws-channel',
  instanceType: 'local',
  clientVersion: '2.0.0',
  minServerVersion: '1.0.0',
  heartbeatInterval: 30000,
  initialRetryDelay: 1000,
  maxRetryDelay: 30000,
  connectionTimeout: 10000,
  pingInterval: 30000,
  pingTimeout: 10000,
};

// ==================== 主类 ====================

/**
 * OpenClaw 微信频道客户端
 *
 * 使用示例：
 * ```typescript
 * const client = new WechatChannelClient({
 *   relayUrl: 'wss://claw.7color.vip/ws-channel',
 *   instanceType: 'local',
 * }, {
 *   onChatRequest: async (msg) => {
 *     // 调用本地 OpenClaw API
 *     const response = await callOpenClaw(msg.content);
 *     return response;
 *   },
 *   onConnect: () => console.log('已连接'),
 *   onDisconnect: () => console.log('已断开'),
 * });
 *
 * await client.connect(deviceInfo);
 * ```
 */
export class WechatChannelClient {
  private config: Required<WechatChannelClientConfig>;
  private callbacks: WechatChannelClientCallbacks;
  private ws: WebSocket | null = null;
  private state: ClientState = {
    connected: false,
    authorized: false,
    deviceId: null,
    openid: null,
    serverVersion: null,
  };
  private heartbeatTimer: NodeJS.Timeout | null = null;
  private retryCount = 0;
  private isConnecting = false;
  private shouldReconnect = true;

  /**
   * 创建客户端实例
   */
  constructor(
    config: WechatChannelClientConfig = {},
    callbacks: WechatChannelClientCallbacks
  ) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.callbacks = callbacks;
  }

  /**
   * 获取当前状态
   */
  getState(): Readonly<ClientState> {
    return { ...this.state };
  }

  /**
   * 连接到中转服务
   */
  async connect(deviceInfo: DeviceInfo): Promise<void> {
    if (this.isConnecting || this.state.connected) {
      return;
    }

    this.isConnecting = true;
    this.state.deviceId = deviceInfo.deviceId;

    try {
      await this._connect(deviceInfo);
      this.retryCount = 0;
    } catch (error) {
      this.isConnecting = false;
      throw error;
    }
  }

  /**
   * 断开连接
   */
  async disconnect(): Promise<void> {
    this.shouldReconnect = false;
    this._stopHeartbeat();

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.state.connected = false;
    this.callbacks.onDisconnect?.();
  }

  /**
   * 发送聊天响应
   */
  async sendChatResponse(openid: string, content: string): Promise<void> {
    const message: ChatResponseMessage = {
      type: 'chat_response',
      openid,
      content,
      client_version: this.config.clientVersion,
    };
    await this._send(message);
  }

  /**
   * 发送状态查询
   */
  async sendStatusQuery(): Promise<void> {
    await this._send({ type: 'status' });
  }

  // ==================== 私有方法 ====================

  /**
   * 内部连接实现
   */
  private async _connect(deviceInfo: DeviceInfo): Promise<void> {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('连接超时'));
        this.ws?.close();
      }, this.config.connectionTimeout);

      this.ws = new WebSocket(this.config.relayUrl, {
        handshakeTimeout: this.config.connectionTimeout,
      });

      // WebSocket 层 ping/pong
      this.ws.on('open', () => {
        clearTimeout(timeout);
        this._sendRegisterMessage(deviceInfo);
      });

      this.ws.on('message', (data: WebSocket.RawData) => {
        this._handleMessage(data);
      });

      this.ws.on('close', () => {
        clearTimeout(timeout);
        this._handleDisconnect();
      });

      this.ws.on('error', (error: Error) => {
        clearTimeout(timeout);
        this.callbacks.onError?.(error);
        reject(error);
      });

      // 等待注册响应
      const onRegistered = (data: WebSocket.RawData) => {
        try {
          const msg = JSON.parse(data.toString()) as WsMessage;
          if (msg.type === 'registered') {
            this.ws?.off('message', onRegistered);
            resolve();
          } else if (msg.type === 'error') {
            this.ws?.off('message', onRegistered);
            reject(new Error(msg.error || '注册失败'));
          }
        } catch {
          // 忽略解析错误，继续等待
        }
      };

      this.ws.on('message', onRegistered);
    });
  }

  /**
   * 发送注册消息
   */
  private _sendRegisterMessage(deviceInfo: DeviceInfo): void {
    const message: RegisterMessage = {
      type: 'register',
      instance_type: this.config.instanceType,
      device_id: deviceInfo.deviceId,
      device_type: deviceInfo.deviceType,
      machine_id: deviceInfo.machineId,
      system_username: deviceInfo.systemUsername,
      client_version: this.config.clientVersion,
      min_server_version: this.config.minServerVersion,
      is_new_device: deviceInfo.isNewDevice,
    };
    this._send(message);
  }

  /**
   * 处理收到的消息
   */
  private _handleMessage(data: WebSocket.RawData): void {
    try {
      const message = JSON.parse(data.toString()) as WsMessage;

      switch (message.type) {
        case 'registered':
          this._handleRegistered(message as RegisteredMessage);
          break;

        case 'chat_request':
          this._handleChatRequest(message as ChatRequestMessage);
          break;

        case 'status_response':
          this._handleStatusResponse(message as StatusResponseMessage);
          break;

        case 'ping':
          this._send({ type: 'pong' });
          break;

        case 'error':
          this.callbacks.onError?.(new Error(message.error || '未知错误'));
          break;

        case 'update_required':
          console.warn('需要更新客户端');
          break;
      }
    } catch (error) {
      console.error('消息解析错误:', error);
    }
  }

  /**
   * 处理注册响应
   */
  private _handleRegistered(message: RegisteredMessage): void {
    this.state.connected = true;
    this.state.serverVersion = message.server_version;
    this.isConnecting = false;

    // 检查是否是恢复连接
    if (message.is_recovery && message.recovered_openid) {
      this.state.openid = message.recovered_openid;
      this.state.authorized = true;
      this.callbacks.onAuthorized?.(message.recovered_openid);
    }

    // 启动心跳
    this._startHeartbeat();

    // 触发连接回调
    this.callbacks.onConnect?.();

    // 如果未授权，触发授权回调
    if (!this.state.authorized && message.auth_url) {
      this.callbacks.onAuthRequired?.(message.auth_url);
    }
  }

  /**
   * 处理聊天请求
   */
  private async _handleChatRequest(message: ChatRequestMessage): Promise<void> {
    try {
      const response = await this.callbacks.onChatRequest(message);
      await this.sendChatResponse(message.openid, response);
    } catch (error) {
      console.error('处理聊天请求失败:', error);
      // 发送错误响应
      await this.sendChatResponse(
        message.openid,
        '⚠️ 处理消息时发生错误，请稍后重试。'
      );
    }
  }

  /**
   * 处理状态响应
   */
  private _handleStatusResponse(message: StatusResponseMessage): void {
    this.state.authorized = message.is_authorized;
    if (message.openid) {
      this.state.openid = message.openid;
    }

    if (message.is_authorized && message.openid) {
      this.callbacks.onAuthorized?.(message.openid);
    }
  }

  /**
   * 处理断开连接
   */
  private _handleDisconnect(): void {
    this.state.connected = false;
    this._stopHeartbeat();
    this.callbacks.onDisconnect?.();

    // 自动重连
    if (this.shouldReconnect) {
      this._scheduleReconnect();
    }
  }

  /**
   * 调度重连
   */
  private _scheduleReconnect(): void {
    this.retryCount++;
    const delay = Math.min(
      this.config.initialRetryDelay * Math.pow(2, this.retryCount - 1),
      this.config.maxRetryDelay
    );

    this.callbacks.onReconnecting?.(this.retryCount, delay);

    setTimeout(() => {
      if (this.shouldReconnect && !this.state.connected) {
        this._reconnect();
      }
    }, delay);
  }

  /**
   * 执行重连
   */
  private async _reconnect(): Promise<void> {
    if (!this.state.deviceId) {
      console.error('无法重连：缺少设备信息');
      return;
    }

    try {
      await this.connect({
        deviceId: this.state.deviceId,
        deviceType: 'bare', // 从配置恢复
        machineId: '',
        systemUsername: '',
        isNewDevice: false,
      });
    } catch (error) {
      console.error('重连失败:', error);
    }
  }

  /**
   * 启动心跳
   */
  private _startHeartbeat(): void {
    this._stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.state.connected) {
        this.sendStatusQuery().catch(console.error);
      }
    }, this.config.heartbeatInterval);
  }

  /**
   * 停止心跳
   */
  private _stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  /**
   * 发送消息
   */
  private async _send(message: WsMessage): Promise<void> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket 未连接');
    }

    return new Promise((resolve, reject) => {
      this.ws!.send(JSON.stringify(message), (error) => {
        if (error) {
          reject(error);
        } else {
          resolve();
        }
      });
    });
  }
}

// ==================== 导出 ====================

export default WechatChannelClient;