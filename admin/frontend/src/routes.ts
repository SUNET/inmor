import HomeView from "./views/HomeView.vue";
import LoginView from "./views/LoginView.vue";
import SubordinatesView from "./views/SubordinatesView.vue";
import TrustMarksView from "./views/TrustMarksView.vue";
import TrustMarkTypesView from "./views/TrustMarkTypesView.vue";

export const routes = [
    {
        path: '/login',
        name: 'login',
        component: LoginView,
        meta: { requiresAuth: false, layout: 'none' },
    },
    {
        path: '/',
        name: 'home',
        component: HomeView,
        meta: { requiresAuth: true },
    },
    {
        path: '/trustmark-types',
        name: 'trustmark-types',
        component: TrustMarkTypesView,
        meta: { requiresAuth: true },
    },
    {
        path: '/trustmarks',
        name: 'trustmarks',
        component: TrustMarksView,
        meta: { requiresAuth: true },
    },
    {
        path: '/subordinates',
        name: 'subordinates',
        component: SubordinatesView,
        meta: { requiresAuth: true },
    },
]
