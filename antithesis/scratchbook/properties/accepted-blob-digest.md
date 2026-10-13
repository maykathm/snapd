# accepted-blob-digest

## Property

**Priority:** P0. **Type:** Safety / `Always`. **Confidence:** high.
Whenever a downloaded, signed ordinary application snap is accepted by successful
`validate-snap`, its complete blob's SHA3-384 and byte size must equal the
independently known authorized fixture for the admitted snap ID/revision.
Retained accepted blobs must still match at a settled observation without an
intervening authorized replacement. Corrupt/wrong-revision content must not be
accepted; retrying or rejecting it is legitimate. Violation can install or retain
the wrong content despite apparently successful lifecycle operations.

Scope answer (verbatim): "just this directory"; `external_references: []`.
Discovery lenses: targeted data integrity and failure recovery.

## Verified Evidence

- [Download task construction](../../../overlord/snapstate/snapstate.go#L939)
  creates `download-snap` followed by `validate-snap`, before the
  [last-before-local-modifications edge](../../../overlord/snapstate/snapstate.go#L971).
- [doValidateSnap](../../../overlord/assertstate/assertmgr.go#L86) hashes the
  actual SnapPath at [line 96](../../../overlord/assertstate/assertmgr.go#L96),
  fetches assertions by that digest, and
  [cross-checks](../../../overlord/assertstate/assertmgr.go#L150) the verified
  revision before checking provenance and returning success.
- [SnapFileSHA3_384](../../../asserts/snap_asserts.go#L526) computes full-file
  SHA3-384/size and encodes the digest using `EncodeDigest`.
  [snapasserts.CrossCheck](../../../asserts/snapasserts/snapasserts.go#L93)
  selects `snap-revision` by digest/provenance, then checks size, snap ID and
  revision against SideInfo. Store download hashes use hex instead; normalize
  encodings or compare raw digest bytes, not unlike strings.
- [Cache size heuristic](../../../store/store_download.go#L121) explicitly
  excludes silent bit rot. [Cache acceptance](../../../store/store_download.go#L153)
  can return nil for a nonempty expected-size file without hashing; caller
  validation is therefore material, not optional evidence.
- [Resume hashing](../../../store/store_download.go#L535) includes existing
  partial bytes. [Completed-partial verification](../../../store/store_download.go#L243)
  checks the full digest; [hash-error retry](../../../store/store_download.go#L257)
  truncates and retries once. [Stream hash check](../../../store/store_download.go#L646)
  is conditional on a nonempty expected hash.
  [Delta verification](../../../store/store_download.go#L898) hashes the rebuilt
  blob before publication when an expected digest is supplied.
- [TestResumeOfCompletedRetriedOnHashFailure](../../../store/store_download_test.go#L291)
  replaces same-size wrong partial bytes and checks final content.
  [TestDownloadCacheHitHappy](../../../store/store_download_test.go#L902)
  succeeds with a symbolic cache key and no network download;
  [TestDownloadCacheHitCorruptRedownloads](../../../store/store_download_test.go#L964)
  tests wrong size, not same-size silent corruption.
- [TestValidateSnap](../../../overlord/assertstate/assertstate_test.go#L678)
  finds the signed revision by digest after success;
  [TestValidateSnapNotFound](../../../overlord/assertstate/assertstate_test.go#L787)
  rejects a blob without matching signatures. These establish useful check
  boundaries, not proof against all interrupted cache/recovery paths.

## Assertion and Placement

Proposed acceptance message: `accepted signed snap blob matches admitted fixture digest`.
Proposed settled-check message: `retained accepted snap blob preserves fixture digest`.
Use distinct `assert.Always(condition, message, details)` callsites with SDK
v0.8.0's `bool, string, map[string]any` arguments. Every eligible acceptance or
retention observation must match; `Sometimes` would conceal corrupt acceptances.

At successful `doValidateSnap` return, test-build instrumentation checks the
computed digest/size against the independent fixture manifest for the admitted
ID/revision and records the acceptance boundary. Reuse that computed digest
for inexpensive SUT guidance, but do not make a duplicate comparison to the
same DownloadInfo the only oracle. The workload independently hashes the actual
blob and compares to its signed-fixture ledger, at a barrier that excludes
affecting handlers, refreshes, deletion and replacement. Record task ID,
ID/revision, acceptance/recovery phase, expected/actual digest and size in
details; messages remain fixed.

**Instrumentation status: missing**, per
[existing-assertions](../existing-assertions.md#L11). Hash checks and ordinary
error returns are existing validation logic, not Antithesis assertions. The
manifest lookup, acceptance observations and barrier are proposed mechanisms,
not existing helpers. Expensive independent hashing belongs in the checker or
an explicitly gated research build.

## Workload, Fault Timing, and Boundaries

Use two distinct signed fixture revisions; retry interrupted transfers, resume
partial files, and reuse cache/target paths after isolated restart. Vary timing
around download publication, cache insertion, validation and lifecycle replay.
If intentionally injecting same-size corrupt cache content, do so only in the
isolated harness: rejection/re-download is permitted, acceptance is not. SUT
guidance distinguishes accepted from merely downloaded bytes; the workload
provides an independent full-content oracle after recovery.

Do not assert digest correctness for every nil `Store.Download`: cache size-only
success is an explicit contract and `validate-snap` is the selected acceptance
boundary. A `.partial` file is not accepted content. Do not assert that an
expected HashError, signature failure or missing blob from completed removal
is itself an integrity violation. Downloads with empty/untrusted metadata,
unasserted local/dangerous installs, components, boot snaps, and external writers
are outside this initial property. Delta-specific fault coverage requires delta
fixtures; hashing evidence alone does not imply the harness exercises them.

## Assumptions

The ledger fixes signed ID/revision, digest and size before admission; the
fixture authority and checker are trusted. Signed ordinary-app installs execute
the validation task. Post-acceptance observations exclude permitted removal
and replacement. Harness-wide storage/fault prerequisites remain in
[deployment-topology](../deployment-topology.md#L55).

## Open Questions

None.

### Investigation Log

#### Does successful download mean a cryptographically accepted blob?

- Examined: cache/partial/delta paths, validation task construction,
  `doValidateSnap`, `CrossCheck`, and the download/validation tests above.
- Found: cache success can be size-only; signed validation hashes the actual
  blob and resolves a signature by digest, then checks ID/revision/size.
- Not found: a full digest guarantee at every `Download` success, especially
  cache hits or empty expected hashes.
- Conclusion: resolved; define acceptance at signed validation and compare
  against the independent fixture, with a separate settled retention check.