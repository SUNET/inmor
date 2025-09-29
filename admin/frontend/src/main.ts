import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router';
import { AdminSDK } from './lib/admin-sdk';
import { routes } from './routes';
import App from './App.vue'

const app = createApp(App);

app.config.globalProperties.$sdk = new AdminSDK({
    apiUrl: new URL('http://localhost:8000'),
});

app.use(createRouter({
    history: createWebHistory(),
    routes,
}));

app.mount('#app');
