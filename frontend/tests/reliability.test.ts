import assert from "node:assert/strict";
import test from "node:test";
import {
  confidenceIsAssessed,
  confidenceLabel,
} from "../src/lib/types/agents";
import {
  MAX_READ_RETRIES,
  isTransientReadFailure,
  readRetryDelay,
  shouldRetryRead,
  shouldRetrySubmission,
} from "../src/lib/api/retry";

test("unresolved findings never display a numeric confidence", () => {
  assert.equal(confidenceIsAssessed("INSUFFICIENT"), false);
  assert.equal(confidenceIsAssessed("REQUIRES VERIFICATION"), false);
  assert.equal(confidenceLabel("INSUFFICIENT", "50%"), "Not assessed");
  assert.equal(confidenceLabel("REQUIRES VERIFICATION", "88%"), "Not assessed");
  assert.equal(confidenceLabel("SUPPORTED", "92%"), "92%");
});

test("poll reads retry only transient gateway and network failures", () => {
  assert.equal(isTransientReadFailure({ status: 502 }), true);
  assert.equal(isTransientReadFailure({ status: 503 }), true);
  assert.equal(isTransientReadFailure({ code: "service_unreachable" }), true);
  assert.equal(isTransientReadFailure({ status: 500 }), false);
  assert.equal(shouldRetryRead({ status: 503 }, MAX_READ_RETRIES - 1), true);
  assert.equal(shouldRetryRead({ status: 503 }, MAX_READ_RETRIES), false);
  assert.equal(readRetryDelay(4), 2_000);
});

test("submission retries require the explicit service_busy code", () => {
  assert.equal(shouldRetrySubmission({ code: "service_busy", status: 503 }, 0), true);
  assert.equal(shouldRetrySubmission({ status: 503 }, 0), false);
});
