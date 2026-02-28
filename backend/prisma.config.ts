/**
 * Prisma 7+ config: datasource URL is set here instead of in schema.prisma.
 * DATABASE_URL is read from backend/.env when running prisma CLI from backend.
 */
import "dotenv/config";
import { defineConfig, env } from "prisma/config";

export default defineConfig({
  schema: "prisma/schema.prisma",
  datasource: {
    url: env("DATABASE_URL"),
  },
});
