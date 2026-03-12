import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  integrations: [
    starlight({
      title: "claude-trace",
      description:
        "Zero-configuration OpenTelemetry observability for Claude Agent SDK",
      customCss: ["./src/styles/custom.css"],
      social: {
        github: "https://github.com/claude-trace/claude-trace",
      },
      editLink: {
        baseUrl:
          "https://github.com/claude-trace/claude-trace/edit/main/site/",
      },
      sidebar: [
        {
          label: "Getting Started",
          items: [
            { label: "Overview", link: "/" },
            { label: "Installation", link: "/getting-started/installation/" },
            { label: "Quickstart", link: "/getting-started/quickstart/" },
            { label: "Core Concepts", link: "/getting-started/concepts/" },
          ],
        },
        {
          label: "Guides",
          items: [
            { label: "Python Integration", link: "/guides/python/" },
            { label: "Security & Privacy", link: "/guides/security/" },
            { label: "Cost Attribution", link: "/guides/cost-attribution/" },
            { label: "Trace Diffing", link: "/guides/trace-diff/" },
          ],
        },
        {
          label: "Reference",
          items: [
            { label: "Semantic Conventions", link: "/reference/semconv/" },
            { label: "Configuration", link: "/reference/configuration/" },
          ],
        },
        {
          label: "Contributing",
          items: [
            { label: "Overview", link: "/contributing/overview/" },
            {
              label: "Development Setup",
              link: "/contributing/development-setup/",
            },
            { label: "Testing Guide", link: "/contributing/testing/" },
            { label: "Rust Guide", link: "/contributing/rust-guide/" },
            {
              label: "Semconv Proposals",
              link: "/contributing/semconv-proposals/",
            },
            {
              label: "Release Process",
              link: "/contributing/release-process/",
            },
          ],
        },
        {
          label: "Internals",
          items: [
            { label: "Architecture", link: "/internals/architecture/" },
            { label: "Span Lifecycle", link: "/internals/span-lifecycle/" },
            { label: "Cost Model", link: "/internals/cost-model/" },
          ],
        },
      ],
      head: [
        {
          tag: "meta",
          attrs: {
            property: "og:image",
            content: "/og-image.png",
          },
        },
        {
          tag: "link",
          attrs: {
            rel: "preconnect",
            href: "https://fonts.googleapis.com",
          },
        },
        {
          tag: "link",
          attrs: {
            rel: "preconnect",
            href: "https://fonts.gstatic.com",
            crossorigin: "",
          },
        },
        {
          tag: "link",
          attrs: {
            rel: "stylesheet",
            href: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap",
          },
        },
      ],
    }),
  ],
});
