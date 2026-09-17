// Import suites into one Node test harness so every assertion is reported even
// in environments that restrict communication between child test processes.
import './api.test.mjs'
import './sse.test.mjs'
import './history.test.mjs'
