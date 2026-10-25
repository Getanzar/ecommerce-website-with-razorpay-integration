const { withAppBuildGradle } = require("expo/config-plugins");

// Expo regenerates android/. Keep the Windows path fix in source configuration.
module.exports = function withWindowsCmakeStaging(config) {
  return withAppBuildGradle(config, (mod) => {
    const marker = "// ZIYAMART_WINDOWS_CMAKE_STAGING";
    if (mod.modResults.language !== "groovy") {
      throw new Error("ZIYAMART Windows CMake staging expects a Groovy app build.gradle.");
    }
    if (!mod.modResults.contents.includes(marker)) {
      if (!mod.modResults.contents.includes("android {")) {
        throw new Error("Cannot find the Android build configuration for CMake staging.");
      }
      mod.modResults.contents = mod.modResults.contents.replace("android {", `android {
    ${marker}
    if (System.getProperty('os.name').toLowerCase().contains('windows')) {
        externalNativeBuild {
            cmake {
                buildStagingDirectory file('../../.cxx')
            }
        }
    }
`);
    }
    return mod;
  });
};
