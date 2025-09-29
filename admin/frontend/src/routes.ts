import SubordinatesView from "./views/SubordinatesView.vue";
import TrustMarksView from "./views/TrustMarksView.vue";
import TrustMarkTypesView from "./views/TrustMarkTypesView.vue";

export const routes = [
    { path: '/trustmark-types', component: TrustMarkTypesView },
    { path: '/trustmarks', component: TrustMarksView },
    { path: '/subordinates', component: SubordinatesView },
]
