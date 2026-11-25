// electron-builder `afterSign` hook (Increment 6): notarizes the signed
// macOS artifact when Apple Developer credentials are present as
// environment variables (populated from GitHub Actions secrets in the
// release workflow) — and skips cleanly, without failing the build, when
// they are not. Apple Developer Program enrollment is not assumed to exist
// yet; this hook is written to work correctly whenever those credentials
// are supplied, not to require them now.
const { notarize } = require("@electron/notarize");

exports.default = async function notarizeHook(context) {
  const { electronPlatformName, appOutDir, packager } = context;
  if (electronPlatformName !== "darwin") return;

  const appleId = process.env.APPLE_ID;
  const applePassword = process.env.APPLE_APP_SPECIFIC_PASSWORD;
  const teamId = process.env.APPLE_TEAM_ID;
  // Notarizing requires a code-signed input -- apple.com rejects an
  // unsigned artifact outright, so attempting it without CSC_LINK would
  // fail the whole release build rather than degrade to an unsigned
  // artifact as intended.
  const isSigned = Boolean(process.env.CSC_LINK);

  if (!isSigned || !appleId || !applePassword || !teamId) {
    // Not "unsigned": a CSC_LINK-signed artifact without APPLE_* is still
    // code-signed, just not notarized, which Gatekeeper still requires to
    // install without a manual override. The release workflow's own
    // `fully_signed` check (release.yml) is what decides the publish-time
    // label/draft status from the complete credential set, not this line.
    const missing = [];
    if (!isSigned) missing.push("CSC_LINK");
    if (!appleId) missing.push("APPLE_ID");
    if (!applePassword) missing.push("APPLE_APP_SPECIFIC_PASSWORD");
    if (!teamId) missing.push("APPLE_TEAM_ID");
    console.log(
      `[notarize] ${missing.join("/")} not set — skipping notarization; ` +
        "this build's artifact is not notarized (Gatekeeper will not treat " +
        "it as a trusted release artifact).",
    );
    return;
  }

  const appName = packager.appInfo.productFilename;
  const appPath = `${appOutDir}/${appName}.app`;

  console.log(`[notarize] Submitting ${appPath} for notarization...`);
  await notarize({
    appPath,
    appleId,
    appleIdPassword: applePassword,
    teamId,
  });
  console.log("[notarize] Notarization complete.");
};
