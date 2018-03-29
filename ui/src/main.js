// The Vue build version to load with the `import` command
// (runtime-only or standalone) has been set in webpack.base.conf with an alias.
import Vue from 'vue'
import VueMoment from 'vue-moment'
import VueLodash from 'vue-lodash'
import 'bootstrap/dist/css/bootstrap.css'
import * as uiv from 'uiv'

import Pastamaker from './Pastamaker'

Vue.use(uiv)
Vue.use(VueMoment)
Vue.use(VueLodash)

Vue.config.productionTip = false

/* eslint-disable no-new */
new Vue({
  el: '#pastamaker',
  components: { Pastamaker },
  template: '<Pastamaker/>'
})
