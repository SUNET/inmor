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
        meta: { requiresAuth: false, layout: 'none', title: 'Login' },
    },
    {
        path: '/access-denied',
        name: 'access-denied',
        component: LoginView,
        meta: { layout: 'none', title: 'Access denied' },
    },
    {
        path: '/service-unavailable',
        name: 'service-unavailable',
        component: LoginView,
        meta: { layout: 'none', title: 'Service unavailable' },
    },
    {
        path: '/',
        name: 'home',
        component: HomeView,
        meta: { requiresAuth: true, title: 'Dashboard' },
    },
    {
        path: '/trustmark-types',
        name: 'trustmark-types',
        component: TrustMarkTypesView,
        meta: { requiresAuth: true, title: 'Trust Mark Types' },
    },
    {
        path: '/trustmarks',
        name: 'trustmarks',
        component: TrustMarksView,
        meta: { requiresAuth: true, title: 'Trust Marks' },
    },
    {
        path: '/subordinates',
        name: 'subordinates',
        component: SubordinatesView,
        meta: { requiresAuth: true, title: 'Subordinates' },
    },
]
