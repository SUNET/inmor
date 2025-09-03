/// <reference types="vite/client" />
import { AdminSDK } from "./lib/admin-sdk/sdk";

declare module 'vue' {
  interface ComponentCustomProperties {
    $sdk: AdminSDK
  }
}