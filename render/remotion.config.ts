import { Config } from "@remotion/cli/config";

// §11.3 hermeticity. Every one of these is a determinism lever, not a
// performance preference.
Config.setVideoImageFormat("png");     // lossless intermediates (§11.4)
Config.setOverwriteOutput(true);
Config.setChromiumDisableWebSecurity(false);
// §11.3: "GPU vs CPU rasterisation → pin, or key on it explicitly."
Config.setChromiumOpenGlRenderer("swangle");
Config.setConcurrency(1);
