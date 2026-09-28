# Source verification scope

The source receipt covers Windows Python regressions, current Edge and Chromium/Firefox browser tests, and the private learning contract. Baseline files contain actual old failures; they are distinct from fault-injection oracle fixtures.

The local browser runner returned failure after three Docker Linux-engine connection attempts. Its current Windows browser stages passed; its Linux fixed-browser stage did not run. Hosted producer and public-release consumer jobs must supply target and publication proof for the new commit.

The existing native quality policy is version 1 and the installed validator requires version 2. It is not native enforcement proof. Direct source checks and the existing mandatory hosted pipeline are the fallback; host policies were not changed.

verification.json intentionally records the pre-publication scope. The final delivery report binds subsequent CI and downloaded-asset receipts to the exact committed revision.
