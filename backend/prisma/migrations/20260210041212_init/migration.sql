-- CreateEnum
CREATE TYPE "user_role" AS ENUM ('advocate', 'admin');

-- CreateEnum
CREATE TYPE "case_status" AS ENUM ('filed', 'registered', 'pending', 'disposed', 'transferred');

-- CreateEnum
CREATE TYPE "case_party_role" AS ENUM ('petitioner', 'respondent', 'appellant', 'defendant');

-- CreateEnum
CREATE TYPE "document_category" AS ENUM ('case_file', 'annexure', 'judgment', 'order', 'misc');

-- CreateEnum
CREATE TYPE "upload_status" AS ENUM ('pending', 'uploading', 'completed', 'failed');

-- CreateEnum
CREATE TYPE "ocr_status" AS ENUM ('not_required', 'pending', 'processing', 'completed', 'failed');

-- CreateEnum
CREATE TYPE "case_event_type" AS ENUM ('hearing', 'order', 'judgment', 'filing', 'notice');

-- CreateEnum
CREATE TYPE "ai_analysis_status" AS ENUM ('pending', 'processing', 'completed', 'failed');

-- CreateEnum
CREATE TYPE "urgency_level" AS ENUM ('low', 'medium', 'high', 'critical');

-- CreateEnum
CREATE TYPE "ai_insight_type" AS ENUM ('bundle_analysis', 'precedents', 'risk_assessment', 'rights_mapping', 'narrative', 'counter_anticipation', 'relief_evaluation');

-- CreateEnum
CREATE TYPE "insight_status" AS ENUM ('pending', 'processing', 'completed', 'failed');

-- CreateEnum
CREATE TYPE "subscription_plan" AS ENUM ('free', 'professional', 'enterprise');

-- CreateEnum
CREATE TYPE "subscription_status" AS ENUM ('active', 'cancelled', 'expired', 'trial');

-- CreateEnum
CREATE TYPE "billing_cycle" AS ENUM ('monthly', 'annually');

-- CreateEnum
CREATE TYPE "payment_method" AS ENUM ('upi', 'card', 'netbanking', 'none');

-- CreateEnum
CREATE TYPE "invoice_status" AS ENUM ('paid', 'pending', 'failed');

-- CreateTable
CREATE TABLE "users" (
    "id" UUID NOT NULL,
    "email" VARCHAR(255) NOT NULL,
    "mobile" VARCHAR(15),
    "password_hash" VARCHAR(255) NOT NULL,
    "khc_advocate_id" VARCHAR(50) NOT NULL,
    "khc_advocate_name" VARCHAR(255) NOT NULL,
    "khc_enrollment_number" VARCHAR(50),
    "role" "user_role" NOT NULL DEFAULT 'advocate',
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "is_verified" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_login_at" TIMESTAMP(3),
    "last_sync_at" TIMESTAMP(3),
    "password_reset_token" VARCHAR(255),
    "password_reset_token_expiry" TIMESTAMP(3),
    "preferences" JSONB NOT NULL DEFAULT '{}',

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "cases" (
    "id" UUID NOT NULL,
    "advocate_id" UUID NOT NULL,
    "case_number" VARCHAR(100),
    "efiling_number" VARCHAR(100) NOT NULL,
    "case_type" VARCHAR(50) NOT NULL,
    "case_year" INTEGER NOT NULL,
    "party_role" "case_party_role" NOT NULL,
    "petitioner_name" TEXT NOT NULL,
    "respondent_name" TEXT NOT NULL,
    "efiling_date" TIMESTAMP(3) NOT NULL,
    "efiling_details" TEXT,
    "bench_type" VARCHAR(50),
    "judge_name" VARCHAR(255),
    "court_number" VARCHAR(50),
    "status" "case_status" NOT NULL DEFAULT 'filed',
    "next_hearing_date" TIMESTAMP(3),
    "khc_source_url" TEXT,
    "last_synced_at" TIMESTAMP(3),
    "sync_status" VARCHAR(50) NOT NULL DEFAULT 'pending',
    "search_vector" TEXT,
    "is_visible" BOOLEAN NOT NULL DEFAULT true,
    "transferred_reason" TEXT,
    "transferred_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "cases_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "documents" (
    "id" UUID NOT NULL,
    "case_id" UUID NOT NULL,
    "khc_document_id" VARCHAR(100) NOT NULL,
    "category" "document_category" NOT NULL,
    "title" VARCHAR(255) NOT NULL,
    "description" TEXT,
    "s3_key" VARCHAR(500) NOT NULL,
    "s3_bucket" VARCHAR(100) NOT NULL DEFAULT 'lawmate-case-pdfs',
    "s3_version_id" VARCHAR(100),
    "file_size" BIGINT NOT NULL,
    "content_type" VARCHAR(50) NOT NULL DEFAULT 'application/pdf',
    "checksum_md5" VARCHAR(32),
    "upload_status" "upload_status" NOT NULL DEFAULT 'pending',
    "uploaded_at" TIMESTAMP(3),
    "upload_error" TEXT,
    "source_url" TEXT,
    "is_ocr_required" BOOLEAN NOT NULL DEFAULT false,
    "ocr_status" "ocr_status" NOT NULL DEFAULT 'not_required',
    "ocr_job_id" VARCHAR(255),
    "extracted_text" TEXT,
    "classification_confidence" DOUBLE PRECISION,
    "ai_metadata" JSONB,
    "is_locked" BOOLEAN NOT NULL DEFAULT false,
    "lock_reason" VARCHAR(255),
    "locked_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "documents_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "case_history" (
    "id" UUID NOT NULL,
    "case_id" UUID NOT NULL,
    "event_type" "case_event_type" NOT NULL,
    "event_date" TIMESTAMP(3) NOT NULL,
    "business_recorded" TEXT NOT NULL,
    "judge_name" VARCHAR(255),
    "bench_type" VARCHAR(50),
    "court_number" VARCHAR(50),
    "next_hearing_date" TIMESTAMP(3),
    "order_document_id" UUID,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "case_history_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ai_analyses" (
    "id" UUID NOT NULL,
    "case_id" UUID NOT NULL,
    "advocate_id" UUID NOT NULL,
    "status" "ai_analysis_status" NOT NULL DEFAULT 'pending',
    "model_version" VARCHAR(50) NOT NULL DEFAULT 'claude-3.5-sonnet',
    "analysis" JSONB,
    "urgency_level" "urgency_level",
    "case_summary" TEXT,
    "processed_at" TIMESTAMP(3),
    "processing_time_seconds" INTEGER,
    "token_count" INTEGER,
    "error_message" TEXT,
    "retry_count" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ai_analyses_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ai_insights" (
    "id" UUID NOT NULL,
    "case_id" UUID NOT NULL,
    "insight_type" "ai_insight_type" NOT NULL,
    "result" JSONB NOT NULL,
    "model" TEXT NOT NULL DEFAULT 'claude-3-5-sonnet-20241022',
    "tokens_used" INTEGER,
    "status" "insight_status" NOT NULL DEFAULT 'completed',
    "error" TEXT,
    "cached" BOOLEAN NOT NULL DEFAULT false,
    "cache_key" VARCHAR(255),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expires_at" TIMESTAMP(3),

    CONSTRAINT "ai_insights_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "hearing_briefs" (
    "id" UUID NOT NULL,
    "case_id" UUID NOT NULL,
    "hearing_date" TIMESTAMP(3) NOT NULL,
    "content" TEXT NOT NULL,
    "focus_areas" TEXT[],
    "bundle_snapshot" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "hearing_briefs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "subscriptions" (
    "id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "plan" "subscription_plan" NOT NULL DEFAULT 'free',
    "status" "subscription_status" NOT NULL DEFAULT 'trial',
    "billing_cycle" "billing_cycle" NOT NULL DEFAULT 'monthly',
    "amount" INTEGER NOT NULL DEFAULT 0,
    "currency" VARCHAR(3) NOT NULL DEFAULT 'INR',
    "start_date" TIMESTAMP(3) NOT NULL,
    "end_date" TIMESTAMP(3) NOT NULL,
    "trial_end_date" TIMESTAMP(3),
    "auto_renew" BOOLEAN NOT NULL DEFAULT true,
    "payment_method" "payment_method",
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "subscriptions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "invoices" (
    "id" UUID NOT NULL,
    "subscription_id" UUID NOT NULL,
    "amount" INTEGER NOT NULL,
    "currency" VARCHAR(3) NOT NULL DEFAULT 'INR',
    "status" "invoice_status" NOT NULL DEFAULT 'pending',
    "invoice_date" TIMESTAMP(3) NOT NULL,
    "due_date" TIMESTAMP(3) NOT NULL,
    "paid_date" TIMESTAMP(3),
    "payment_method" "payment_method",
    "invoice_url" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "invoices_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "usage_tracking" (
    "id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "period_start" TIMESTAMP(3) NOT NULL,
    "period_end" TIMESTAMP(3) NOT NULL,
    "cases_count" INTEGER NOT NULL DEFAULT 0,
    "documents_count" INTEGER NOT NULL DEFAULT 0,
    "storage_used_bytes" BIGINT NOT NULL DEFAULT 0,
    "ai_analyses_used" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "usage_tracking_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "users_email_key" ON "users"("email");

-- CreateIndex
CREATE UNIQUE INDEX "users_mobile_key" ON "users"("mobile");

-- CreateIndex
CREATE UNIQUE INDEX "users_khc_advocate_id_key" ON "users"("khc_advocate_id");

-- CreateIndex
CREATE INDEX "idx_user_login" ON "users"("email", "is_active");

-- CreateIndex
CREATE INDEX "idx_user_khc" ON "users"("khc_advocate_id", "is_active");

-- CreateIndex
CREATE UNIQUE INDEX "cases_efiling_number_key" ON "cases"("efiling_number");

-- CreateIndex
CREATE INDEX "idx_case_advocate_status" ON "cases"("advocate_id", "status", "is_visible");

-- CreateIndex
CREATE INDEX "idx_case_advocate_hearing" ON "cases"("advocate_id", "next_hearing_date");

-- CreateIndex
CREATE UNIQUE INDEX "documents_s3_key_key" ON "documents"("s3_key");

-- CreateIndex
CREATE INDEX "idx_doc_case_category" ON "documents"("case_id", "category");

-- CreateIndex
CREATE INDEX "idx_history_case_date" ON "case_history"("case_id", "event_date");

-- CreateIndex
CREATE UNIQUE INDEX "ai_analyses_case_id_key" ON "ai_analyses"("case_id");

-- CreateIndex
CREATE INDEX "idx_ai_advocate_urgency" ON "ai_analyses"("advocate_id", "urgency_level");

-- CreateIndex
CREATE INDEX "idx_insight_case_type" ON "ai_insights"("case_id", "insight_type");

-- CreateIndex
CREATE INDEX "idx_insight_cache" ON "ai_insights"("cache_key");

-- CreateIndex
CREATE INDEX "idx_brief_case_hearing" ON "hearing_briefs"("case_id", "hearing_date");

-- CreateIndex
CREATE INDEX "idx_subscription_user_status" ON "subscriptions"("user_id", "status");

-- CreateIndex
CREATE INDEX "idx_invoice_subscription_status" ON "invoices"("subscription_id", "status");

-- CreateIndex
CREATE INDEX "idx_usage_user_period" ON "usage_tracking"("user_id", "period_end");

-- CreateIndex
CREATE UNIQUE INDEX "usage_tracking_user_id_period_start_key" ON "usage_tracking"("user_id", "period_start");

-- AddForeignKey
ALTER TABLE "cases" ADD CONSTRAINT "cases_advocate_id_fkey" FOREIGN KEY ("advocate_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "documents" ADD CONSTRAINT "documents_case_id_fkey" FOREIGN KEY ("case_id") REFERENCES "cases"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "case_history" ADD CONSTRAINT "case_history_case_id_fkey" FOREIGN KEY ("case_id") REFERENCES "cases"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "case_history" ADD CONSTRAINT "case_history_order_document_id_fkey" FOREIGN KEY ("order_document_id") REFERENCES "documents"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ai_analyses" ADD CONSTRAINT "ai_analyses_case_id_fkey" FOREIGN KEY ("case_id") REFERENCES "cases"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ai_analyses" ADD CONSTRAINT "ai_analyses_advocate_id_fkey" FOREIGN KEY ("advocate_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "hearing_briefs" ADD CONSTRAINT "hearing_briefs_case_id_fkey" FOREIGN KEY ("case_id") REFERENCES "cases"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "subscriptions" ADD CONSTRAINT "subscriptions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "invoices" ADD CONSTRAINT "invoices_subscription_id_fkey" FOREIGN KEY ("subscription_id") REFERENCES "subscriptions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "usage_tracking" ADD CONSTRAINT "usage_tracking_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
