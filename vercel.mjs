const origin = process.env.BACKEND_ORIGIN?.replace(/\/$/, "");

if (!origin || !/^https:\/\/[^/]+$/.test(origin)) {
  throw new Error("Set BACKEND_ORIGIN to the HTTPS URL of the Render service.");
}

export const config = {
  framework: null,
  buildCommand: "node scripts/build-vercel.mjs",
  outputDirectory: "vercel-public",
  rewrites: [
    { source: "/:path*", destination: `${origin}/:path*` },
  ],
};
