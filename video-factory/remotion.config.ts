import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);

// Video quality settings
Config.setJpegQuality(80);

// Concurrency for rendering
Config.setConcurrency(4);

// Output codec
Config.setCodec("h264");
