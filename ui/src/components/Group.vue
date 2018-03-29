<template>
    <div class="group">
    <table class="table table-condensed multiple">
     <thead>
     <tr>
         <th class="title">
            <a :href="pulls_url">{{ owner }}/{{ repo }}</a> - {{ branch }}
         </th>
         <th class="state"><span class="glyphicon glyphicon-comment"></span></th>
         <th class="state"><span class="glyphicon glyphicon-list"></span></th>
         <th class="state"><span class="glyphicon glyphicon-file"></span></th>
         <th class="last-updated">Last updated</th>
         <th class="state" title="Indicates its status">CI</th>
         <th class="mergeable" title="Mergeable status"><span class="glyphicon glyphicon-random" title="Mergeable"></span></th>
         <th class="milestone" title="Milestone"><span class="glyphicon glyphicon-gift" title="Milestone"></span></th>
         <th class="reviews"><span class="glyphicon glyphicon-thumbs-up"></span></th>
         <th class="reviews"><span class="glyphicon glyphicon-thumbs-down"></span></th>
         <th class="queue">Weight
         </th>
     </tr>
     </thead>
     <tbody>
         <template v-for="pull in pulls">
             <Pull :key="pull.number" :pull="pull"></Pull>
             <TravisDetail :key="'travis' + pull.number" :pull="pull"></TravisDetail>
         </template>
     </tbody>
    </table>
    </div>
</template>

<script>
import Pull from './Pull'
import TravisDetail from './TravisDetail'

export default {
  name: 'Group',
  components: {
    Pull,
    TravisDetail
  },
  props: ['group'],
  data () {
    return this._.merge(this.group, {
      pulls_url: 'https://github.com/' + this.owner + '/' + this.repo + '/pulls'
    })
  }
}
</script>
