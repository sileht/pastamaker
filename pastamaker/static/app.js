angular.module('triage', [
    'ngRoute',
    'triage.controllers',
    'angularMoment',
    'classy'
])

.config(['$routeProvider', '$locationProvider', function ($routeProvider, $locationProvider) {
    $locationProvider.html5Mode(true);
    $routeProvider.when('/', {
        templateUrl: "/static/partials/table.html",
        controller: 'PullsController'
    });
}])

;
