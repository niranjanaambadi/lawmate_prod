export type LegalSection = {
  heading?: string;
  body: string[];
  bullets?: string[];
  subsections?: { heading: string; body: string[]; bullets?: string[] }[];
};

export type LegalDocument = {
  title: string;
  subtitle: string;
  intro: string[];
  sections: LegalSection[];
  acknowledgment: string;
};

export const privacyPolicy: LegalDocument = {
  title: "LAWMATE PRIVACY POLICY",
  subtitle: "Last Updated: March 2, 2026 · Compliant with Information Technology Act, 2000 and SPDI Rules, 2011",
  intro: [
    'LawMate ("we," "us," or "our") is committed to protecting the privacy and confidentiality of information entrusted to us by advocates practicing before the Kerala High Court. This Privacy Policy describes how we collect, use, store, process, and protect your personal and professional data in compliance with the Information Technology Act, 2000, the Information Technology (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules, 2011 ("SPDI Rules"), and other applicable Indian laws.',
    "By using the LawMate Platform, you consent to the collection, use, and processing of your information as described in this Privacy Policy. If you do not agree with this Privacy Policy, please do not use the Platform.",
  ],
  sections: [
    {
      heading: "1. SCOPE AND DEFINITIONS",
      body: [],
      subsections: [
        {
          heading: "1.1 Scope",
          body: [
            "This Privacy Policy applies to all personal data and sensitive personal data or information ("SPDI") collected through the LawMate Platform from advocates enrolled with the Kerala High Court Bar Association.",
          ],
        },
        {
          heading: "1.2 Definitions",
          body: [],
          bullets: [
            "Personal Data: Information that relates to a natural person and can be used to identify that person, including name, email address, phone number, and professional credentials.",
            "Sensitive Personal Data or Information (SPDI): As defined under the SPDI Rules, includes passwords, financial information, and any other information designated as sensitive by the Central Government. For purposes of this Policy, professional legal data and case files are treated with the same level of protection as SPDI.",
            "Professional Data: Case files, legal documents, case bundles, client information, court filings, legal research, and other materials uploaded or generated through the Platform.",
          ],
        },
      ],
    },
    {
      heading: "2. INFORMATION WE COLLECT",
      body: [],
      subsections: [
        {
          heading: "2.1 Information You Provide Directly",
          body: [],
          bullets: [
            "Account Registration Information: Name, email address, mobile number, Kerala High Court Bar Association enrollment number, professional address, and verification documents.",
            "Authentication Credentials: Password and multi-factor authentication tokens (stored in encrypted form).",
            "Professional Data: All case files, documents, bundles, legal briefs, client information, court filings, and other materials you upload to the Platform.",
            "Payment Information: Billing details and payment transaction information (processed through third-party payment gateways; we do not store complete credit card numbers).",
            "Communications: Any correspondence you send to us via email, support tickets, or in-platform messaging.",
          ],
        },
        {
          heading: "2.2 Information Collected Automatically",
          body: [],
          bullets: [
            "Usage Data: Log files recording your interactions with the Platform, including IP address, browser type, device information, access times, pages viewed, and actions performed.",
            "Cookies and Tracking Technologies: Session cookies, authentication tokens, and analytics cookies to maintain your login session and improve Platform functionality. You may disable cookies through your browser settings, but this may limit Platform functionality.",
            "Performance Metrics: Technical metrics related to Platform performance, error logs, and service reliability data.",
          ],
        },
      ],
    },
    {
      heading: "3. HOW WE USE YOUR INFORMATION",
      body: [],
      subsections: [
        {
          heading: "3.1 Service Delivery",
          body: ["We use your information to:"],
          bullets: [
            "Provide access to the LawMate Platform and its features;",
            "Process and store your case documents securely;",
            "Generate AI-powered legal research, case summaries, and productivity tools;",
            "Enable search and retrieval functionality within your case files;",
            "Authenticate your identity and maintain account security.",
          ],
        },
        {
          heading: "3.2 Communication and Support",
          body: [],
          bullets: [
            "Send service-related notifications, including account updates, security alerts, and system maintenance notices;",
            "Respond to your inquiries and provide customer support;",
            "Send subscription renewal reminders and billing notifications.",
          ],
        },
        {
          heading: "3.3 Platform Improvement and Security",
          body: [],
          bullets: [
            "Monitor Platform performance, diagnose technical issues, and improve service reliability;",
            "Detect and prevent fraud, unauthorized access, and security threats;",
            "Conduct internal analytics on usage patterns to improve features (using aggregated, non-identifiable data only);",
            "Enforce our Terms of Use and legal obligations.",
          ],
        },
        {
          heading: "3.4 Legal Compliance",
          body: [
            "Comply with applicable laws, regulations, court orders, or government requests; respond to legal process; and protect our rights and property.",
          ],
        },
        {
          heading: "3.5 No Cross-User Data Use",
          body: [
            "We NEVER use your Professional Data to train AI models, improve services for other users, or create aggregated datasets. Your case files and legal work product remain exclusively yours and are processed only for your benefit.",
          ],
        },
      ],
    },
    {
      heading: "4. DATA STORAGE, PROCESSING, AND SECURITY",
      body: [],
      subsections: [
        {
          heading: "4.1 Storage Infrastructure",
          body: ["Your data is stored on secure Amazon Web Services (AWS) infrastructure, specifically:"],
          bullets: [
            "AWS S3 (Simple Storage Service) for document storage with per-user bucket isolation;",
            "Data is stored in AWS Asia Pacific (Mumbai) region to ensure data residency within India;",
            "Backup copies are maintained in geographically separated AWS availability zones for disaster recovery.",
          ],
        },
        {
          heading: "4.2 AI Processing",
          body: ["AI-powered features utilize AWS Bedrock, Amazon's managed AI service. Processing is performed as follows:"],
          bullets: [
            "Each user's documents are processed in isolated execution contexts;",
            "AWS Bedrock does not retain or use your data to train foundation models;",
            "All processing occurs within AWS Mumbai region infrastructure;",
            "AI-generated outputs are immediately returned to you and not stored by AWS Bedrock.",
          ],
        },
        {
          heading: "4.3 Per-User Data Isolation",
          body: ["We implement strict multi-tenant security measures:"],
          bullets: [
            "Each user account has a unique storage partition with separate encryption keys;",
            "Role-based access controls (RBAC) prevent cross-user data access;",
            "Database records are tagged with user identifiers and query-level access filters;",
            "All API requests include authentication tokens verified before data access;",
            "Comprehensive audit logs track all data access events with user identity verification.",
          ],
        },
        {
          heading: "4.4 Encryption Standards",
          body: [],
          bullets: [
            "Encryption at Rest: All stored data is encrypted using AES-256 encryption;",
            "Encryption in Transit: All data transmission uses TLS 1.2 or higher;",
            "Password Hashing: User passwords are hashed using bcrypt with per-user salts;",
            "Key Management: Encryption keys are managed through AWS Key Management Service (KMS) with automatic rotation.",
          ],
        },
        {
          heading: "4.5 Access Controls",
          body: [],
          bullets: [
            "Access to production systems is restricted to authorized personnel only;",
            "All administrative access is logged and requires multi-factor authentication;",
            "Personnel access is granted on a principle of least privilege and need-to-know basis;",
            "All employees and contractors sign confidentiality agreements before accessing any systems.",
          ],
        },
        {
          heading: "4.6 Security Monitoring",
          body: [
            "We employ continuous security monitoring including intrusion detection, vulnerability scanning, regular security audits, and incident response procedures compliant with ISO 27001 framework.",
          ],
        },
      ],
    },
    {
      heading: "5. DATA SHARING AND DISCLOSURE",
      body: [],
      subsections: [
        {
          heading: "5.1 No Sharing with Other Users",
          body: [
            "We NEVER share your Professional Data with any other LawMate user. Each advocate's case files, documents, and work product remain completely isolated and private.",
          ],
        },
        {
          heading: "5.2 Third-Party Service Providers",
          body: ["We engage limited third-party service providers who process data on our behalf under strict contractual obligations:"],
          bullets: [
            "Amazon Web Services (AWS): Cloud infrastructure, storage, and AI processing services;",
            "Payment Processors: Third-party gateways for subscription billing (Razorpay, Stripe, etc.);",
            "Email Service Providers: For transactional emails and service notifications;",
            "Analytics Providers: For aggregated, anonymized usage analytics (no Personal Data or Professional Data is shared).",
          ],
        },
        {
          heading: "5.3 Legal Obligations",
          body: ["We may disclose your information if required by law, court order, or government authority, including:"],
          bullets: [
            "Compliance with legal process (subpoenas, warrants, court orders);",
            "Protection of LawMate's legal rights and property;",
            "Prevention of fraud or illegal activities;",
            "Response to requests from law enforcement or regulatory authorities.",
          ],
        },
        {
          heading: "5.4 Business Transfers",
          body: [
            "In the event of a merger, acquisition, reorganization, or sale of assets, your information may be transferred to the acquiring entity. We will notify you of any such change and ensure that the acquiring entity is bound by equivalent privacy protections.",
          ],
        },
        {
          heading: "5.5 Consent-Based Sharing",
          body: [
            "We will not share your Personal Data or Professional Data with any third party for any other purpose without obtaining your explicit written consent.",
          ],
        },
      ],
    },
    {
      heading: "6. DATA RETENTION AND DELETION RIGHTS",
      body: [],
      subsections: [
        {
          heading: "6.1 Retention Period",
          body: [],
          bullets: [
            "Active Account Data: Retained for the duration of your active subscription;",
            "Inactive Account Data: Retained for ninety (90) days after account cancellation or expiration;",
            "Backup Data: Retained for up to one hundred eighty (180) days for disaster recovery purposes;",
            "Billing Records: Retained for seven (7) years for tax compliance and accounting purposes;",
            "Audit Logs: Retained for two (2) years for security monitoring and compliance purposes.",
          ],
        },
        {
          heading: "6.2 Right to Deletion",
          body: ["You have the right to request deletion of your Personal Data and Professional Data at any time. To request deletion:"],
          bullets: [
            "Send a written request to privacy@lawmate.in;",
            "We will delete your data within thirty (30) days of receiving your request;",
            "Deletion includes all primary data, copies, and backups (except where retention is legally required);",
            "We will provide written confirmation once deletion is complete.",
          ],
        },
        {
          heading: "6.3 Data Export",
          body: [
            "Before requesting deletion, you may export your data in machine-readable format (JSON or CSV). Export requests are processed within fifteen (15) business days.",
          ],
        },
        {
          heading: "6.4 Exceptions to Deletion",
          body: [
            "We may retain certain information if required by law, for dispute resolution, to enforce agreements, or for legitimate business purposes (such as fraud prevention). Any such retention will be limited to the minimum necessary period.",
          ],
        },
      ],
    },
    {
      heading: "7. YOUR RIGHTS UNDER INDIAN LAW",
      body: ["Under the Information Technology Act, 2000 and SPDI Rules, 2011, you have the following rights:"],
      subsections: [
        {
          heading: "7.1 Right to Access",
          body: [
            "You may request access to your Personal Data and Professional Data at any time through your account dashboard or by contacting privacy@lawmate.in.",
          ],
        },
        {
          heading: "7.2 Right to Correction",
          body: [
            "You may update or correct your Personal Data through your account settings. For corrections requiring manual intervention, contact support@lawmate.in.",
          ],
        },
        {
          heading: "7.3 Right to Withdrawal of Consent",
          body: [
            "You may withdraw your consent for data processing at any time by terminating your account. Note that withdrawal of consent will prevent you from using the Platform.",
          ],
        },
        {
          heading: "7.4 Right to Data Portability",
          body: [
            "You have the right to receive your data in a structured, commonly used, and machine-readable format for transfer to another service provider.",
          ],
        },
        {
          heading: "7.5 Right to Deletion",
          body: ["You may request deletion of your data as described in Section 6.2."],
        },
        {
          heading: "7.6 Right to Grievance Redressal",
          body: [
            "If you have any concerns or complaints regarding data protection, you may contact our Grievance Officer (details in Section 10). We will respond to all rights requests within thirty (30) days.",
          ],
        },
      ],
    },
    {
      heading: "8. COOKIES AND TRACKING TECHNOLOGIES",
      body: [],
      subsections: [
        {
          heading: "8.1 Types of Cookies We Use",
          body: [],
          bullets: [
            "Essential Cookies: Required for authentication, session management, and security. These cannot be disabled without preventing Platform access.",
            "Functional Cookies: Remember your preferences, language settings, and customization choices.",
            "Analytics Cookies: Collect aggregated, anonymized usage data to improve Platform performance (no Personal Data or Professional Data is collected).",
          ],
        },
        {
          heading: "8.2 Cookie Management",
          body: [
            "You can manage cookie preferences through your browser settings. However, disabling essential cookies will prevent you from accessing the Platform.",
          ],
        },
        {
          heading: "8.3 No Third-Party Advertising",
          body: ["We do not use cookies for advertising or share cookie data with advertising networks."],
        },
      ],
    },
    {
      heading: "9. DATA BREACH NOTIFICATION AND INCIDENT RESPONSE",
      body: [],
      subsections: [
        {
          heading: "9.1 Incident Response Plan",
          body: ["We maintain a comprehensive incident response plan to detect, contain, and remediate security incidents. Our procedures include:"],
          bullets: [
            "24/7 security monitoring and automated alerting systems;",
            "Incident triage and severity assessment within four (4) hours of detection;",
            "Containment measures to prevent further unauthorized access;",
            "Forensic investigation to determine scope and impact;",
            "Remediation and security hardening to prevent recurrence.",
          ],
        },
        {
          heading: "9.2 Notification Requirements",
          body: ["In the event of a data breach affecting your Personal Data or Professional Data, we will:"],
          bullets: [
            "Notify you within seventy-two (72) hours of becoming aware of the breach;",
            "Provide details about the nature of the breach, data affected, and potential impact;",
            "Inform you of the remediation measures taken;",
            "Recommend steps you should take to protect your account and data;",
            "Notify relevant regulatory authorities as required by law.",
          ],
        },
        {
          heading: "9.3 Your Responsibilities",
          body: [
            "You must immediately notify us at security@lawmate.in if you suspect any unauthorized access to your account or any security vulnerability in the Platform.",
          ],
        },
      ],
    },
    {
      heading: "10. GRIEVANCE OFFICER AND CONTACT INFORMATION",
      body: [],
      subsections: [
        {
          heading: "10.1 Grievance Redressal",
          body: [
            "In accordance with Rule 5(9) of the SPDI Rules, 2011, we have designated a Grievance Officer to address your concerns regarding data protection and privacy.",
            "Grievance Officer: Email: grievance@lawmate.in · Address: [To be updated with registered office address]",
          ],
        },
        {
          heading: "10.2 Response Timeline",
          body: [
            "The Grievance Officer will acknowledge receipt of your complaint within forty-eight (48) hours and will resolve the complaint within thirty (30) days.",
          ],
        },
        {
          heading: "10.3 Additional Contacts",
          body: [],
          bullets: [
            "Privacy Inquiries: privacy@lawmate.in",
            "Security Reports: security@lawmate.in",
            "General Support: support@lawmate.in",
          ],
        },
      ],
    },
    {
      heading: "11. DATA RESIDENCY AND INTERNATIONAL TRANSFERS",
      body: [],
      subsections: [
        {
          heading: "11.1 Data Residency",
          body: [
            "All Personal Data and Professional Data is stored and processed within India using AWS infrastructure in the Asia Pacific (Mumbai) region. We maintain data residency within Indian jurisdiction to ensure compliance with local laws.",
          ],
        },
        {
          heading: "11.2 No International Transfers",
          body: [
            "We do not transfer your data outside of India. In the rare event that international data transfer becomes necessary for service delivery, we will:",
          ],
          bullets: [
            "Obtain your explicit written consent before any transfer;",
            "Ensure that the receiving jurisdiction provides adequate data protection standards;",
            "Execute Standard Contractual Clauses or equivalent legal safeguards;",
            "Notify you of the countries to which data will be transferred and the safeguards in place.",
          ],
        },
      ],
    },
    {
      heading: "12. CHILDREN'S PRIVACY",
      body: [
        "The LawMate Platform is intended exclusively for use by legal professionals who are at least 18 years of age. We do not knowingly collect information from individuals under 18 years of age. If we become aware that we have collected Personal Data from a person under 18, we will delete such information immediately.",
      ],
    },
    {
      heading: "13. CHANGES TO THIS PRIVACY POLICY",
      body: [],
      subsections: [
        {
          heading: "13.1 Notification of Changes",
          body: [
            "We may update this Privacy Policy from time to time to reflect changes in our practices, legal requirements, or service features. Material changes will be communicated to you via:",
          ],
          bullets: [
            "Email notification to your registered email address;",
            "Prominent notice on the Platform login page;",
            "In-platform notification upon your next login.",
          ],
        },
        {
          heading: "13.2 Effective Date",
          body: [
            "Changes will take effect thirty (30) days after notification, except where immediate changes are required by law.",
          ],
        },
        {
          heading: "13.3 Continued Use",
          body: [
            "Your continued use of the Platform after the effective date constitutes acceptance of the updated Privacy Policy. If you do not agree to the changes, you must discontinue use and may request account termination and data deletion.",
          ],
        },
      ],
    },
    {
      heading: "14. LEGAL COMPLIANCE STATEMENT",
      body: ["This Privacy Policy is designed to comply with the following Indian laws and regulations:"],
      bullets: [
        "Information Technology Act, 2000;",
        "Information Technology (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules, 2011;",
        "Information Technology (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021;",
        "Indian Evidence Act, 1872 (as applicable to electronic records);",
        "Any other applicable data protection and privacy regulations in India.",
      ],
    },
  ],
  acknowledgment:
    "BY CREATING AN ACCOUNT, UPLOADING DATA TO THE PLATFORM, OR USING LAWMATE SERVICES, YOU ACKNOWLEDGE THAT YOU HAVE READ, UNDERSTOOD, AND CONSENT TO THE COLLECTION, USE, STORAGE, AND PROCESSING OF YOUR PERSONAL DATA AND PROFESSIONAL DATA AS DESCRIBED IN THIS PRIVACY POLICY. You confirm that you have the legal authority to consent to this Privacy Policy and that all information provided to LawMate is accurate and complete.",
};

export const termsOfUse: LegalDocument = {
  title: "LAWMATE TERMS OF USE",
  subtitle: "Last Updated: March 2, 2026 · Governed by the Laws of India",
  intro: [
    'These Terms of Use ("Terms") constitute a legally binding agreement between you ("User," "you," or "your") and LawMate ("we," "us," or "our"), governing your access to and use of the LawMate platform ("Platform" or "Service"). By accessing or using the Platform, you acknowledge that you have read, understood, and agree to be bound by these Terms and our Privacy Policy.',
    "IF YOU DO NOT AGREE TO THESE TERMS, YOU MUST NOT ACCESS OR USE THE PLATFORM.",
  ],
  sections: [
    {
      heading: "1. SERVICE ELIGIBILITY AND VERIFICATION",
      body: [],
      subsections: [
        {
          heading: "1.1 Verified Lawyers Only",
          body: [
            "The LawMate Platform is exclusively designed for and restricted to verified advocates enrolled with the Kerala High Court Bar Association. Use of this Platform is strictly limited to legal professionals authorized to practice law before the Kerala High Court.",
          ],
        },
        {
          heading: "1.2 Verification Requirements",
          body: ["To access the Platform, you must:"],
          bullets: [
            "Provide valid Kerala High Court Bar Association enrollment number;",
            "Submit proof of current enrollment status with the Bar Association;",
            "Provide professional contact information (email, mobile number);",
            "Maintain active enrollment status throughout your use of the Platform.",
          ],
        },
        {
          heading: "1.3 Non-Transferable Access",
          body: [
            "Your account is personal and non-transferable. You may not share your login credentials with any other person, including other advocates, junior associates, or office staff. Each authorized user must maintain a separate verified account.",
          ],
        },
        {
          heading: "1.4 Suspension or Termination",
          body: [
            "We reserve the right to suspend or terminate your account immediately if: (i) you fail to maintain valid Bar Association enrollment; (ii) you share your account credentials; (iii) you violate these Terms; or (iv) we receive credible complaints regarding misuse of the Platform.",
          ],
        },
      ],
    },
    {
      heading: "2. DATA OWNERSHIP, CONSENT, AND RESTRICTIONS",
      body: [],
      subsections: [
        {
          heading: "2.1 Your Data Remains Yours",
          body: [
            'All case files, documents, bundles, notes, and any other materials you upload to the Platform (collectively, "Your Data") remain your exclusive property. You retain all intellectual property rights, ownership, and control over Your Data. LawMate claims no ownership rights over Your Data.',
          ],
        },
        {
          heading: "2.2 Explicit Consent for Processing",
          body: [
            "By uploading Your Data to the Platform, you grant LawMate a limited, non-exclusive, revocable license to process, store, and analyze Your Data solely for the purpose of providing Services to you. This includes:",
          ],
          bullets: [
            "Processing documents using AI-powered analysis tools (including AWS Bedrock);",
            "Storing documents securely in encrypted cloud storage (AWS S3);",
            "Generating case summaries, legal research insights, and productivity tools;",
            "Providing search and retrieval functionality within your own case files.",
          ],
        },
        {
          heading: "2.3 Absolute Prohibition on Data Sharing or Cross-Use",
          body: [
            "We implement strict data isolation to ensure that Your Data is never accessible to, shared with, or used to benefit any other user. Specifically:",
          ],
          bullets: [
            "Your Data is stored in logically and physically segregated storage partitions specific to your account;",
            "AI processing is performed exclusively on Your Data in isolation—no cross-contamination with other users' data;",
            "Your Data is never used to train, improve, or enhance AI models for other users;",
            "No outputs, insights, or summaries generated from Your Data are made available to other users;",
            "We do not create aggregated datasets, anonymized insights, or generalized knowledge bases from Your Data.",
          ],
        },
        {
          heading: "2.4 Prohibition on Unauthorized Distribution",
          body: [
            "You may not distribute, republish, or share Your Data with unauthorized third parties through the Platform. Any sharing of case documents must comply with applicable professional ethics rules and client confidentiality obligations.",
          ],
        },
        {
          heading: "2.5 Client Consent and Professional Responsibility",
          body: [
            "You represent and warrant that you have obtained all necessary consents from your clients to upload and process their confidential case information on the Platform. You remain solely responsible for complying with your professional obligations under the Bar Council of India Rules, Advocates Act 1961, and applicable confidentiality requirements.",
          ],
        },
      ],
    },
    {
      heading: "3. INTELLECTUAL PROPERTY RIGHTS",
      body: [],
      subsections: [
        {
          heading: "3.1 LawMate's Intellectual Property",
          body: [
            'The Platform, including all software, algorithms, AI models, user interfaces, design elements, trademarks, logos, and proprietary technology ("LawMate IP"), is and remains the exclusive property of LawMate. You acquire no ownership rights in LawMate IP through your use of the Platform.',
          ],
        },
        {
          heading: "3.2 Your Intellectual Property",
          body: [
            "All legal research, case briefs, arguments, pleadings, and other professional work product you create or upload constitute your intellectual property. LawMate does not claim ownership of any legal work product or professional outputs you generate.",
          ],
        },
        {
          heading: "3.3 AI-Generated Outputs",
          body: [
            'Summaries, insights, research notes, and other outputs generated by the Platform\'s AI tools based on Your Data ("AI Outputs") are provided to you for your exclusive use. You retain all rights to AI Outputs derived from Your Data. LawMate does not retain copies of AI Outputs beyond what is necessary for service delivery.',
          ],
        },
        {
          heading: "3.4 Public Legal Information",
          body: [
            "The Platform may incorporate publicly available legal information, including Supreme Court and Kerala High Court judgments, statutes, and legal precedents. Such public information remains in the public domain and is not subject to proprietary claims by either party.",
          ],
        },
      ],
    },
    {
      heading: "4. DISCLAIMERS AND LIMITATIONS OF AI SERVICES",
      body: [],
      subsections: [
        {
          heading: "4.1 Not Legal Advice",
          body: [
            "THE PLATFORM IS A PRODUCTIVITY AND DOCUMENT MANAGEMENT TOOL. IT DOES NOT PROVIDE LEGAL ADVICE, AND NO CONTENT GENERATED BY THE PLATFORM CONSTITUTES LEGAL ADVICE OR CREATES AN ATTORNEY-CLIENT RELATIONSHIP. All AI-generated outputs must be independently reviewed and verified by you before use in any legal proceeding.",
          ],
        },
        {
          heading: "4.2 Professional Judgment Required",
          body: [
            "You acknowledge that AI tools may produce incomplete, inaccurate, or contextually inappropriate outputs. You are solely responsible for exercising professional judgment, verifying all AI-generated content, and ensuring compliance with legal and ethical standards.",
          ],
        },
        {
          heading: "4.3 No Warranty of Accuracy",
          body: [
            "While we strive for accuracy, we make no warranties regarding the completeness, reliability, or accuracy of AI-generated summaries, legal research, or case insights. You use the Platform's outputs at your own risk.",
          ],
        },
        {
          heading: "4.4 Supplementary Tool",
          body: [
            "The Platform is designed to enhance your efficiency and productivity, not to replace your professional expertise. All final legal work product, court filings, and client advice must reflect your independent professional judgment.",
          ],
        },
      ],
    },
    {
      heading: "5. LIMITATION OF LIABILITY AND INDEMNIFICATION",
      body: [],
      subsections: [
        {
          heading: "5.1 No Liability for Professional Errors",
          body: [
            "TO THE MAXIMUM EXTENT PERMITTED BY INDIAN LAW, LAWMATE SHALL NOT BE LIABLE FOR ANY PROFESSIONAL ERRORS, OMISSIONS, OR LOSSES ARISING FROM YOUR USE OF THE PLATFORM, INCLUDING BUT NOT LIMITED TO:",
          ],
          bullets: [
            "Missed deadlines or procedural errors;",
            "Inaccurate AI-generated legal research or case analysis;",
            "Loss of cases, claims, or professional malpractice actions;",
            "Damage to professional reputation or client relationships;",
            "Any consequential, indirect, incidental, or punitive damages.",
          ],
        },
        {
          heading: "5.2 Maximum Liability Cap",
          body: [
            "In no event shall LawMate's aggregate liability to you for all claims arising out of or related to these Terms or your use of the Platform exceed the total amount paid by you to LawMate in the twelve (12) months preceding the claim, or ₹10,000 (Rupees Ten Thousand), whichever is less.",
          ],
        },
        {
          heading: "5.3 Service Availability",
          body: [
            "We do not guarantee uninterrupted or error-free service. The Platform may experience downtime due to maintenance, technical issues, or circumstances beyond our control. We are not liable for any losses resulting from service interruptions.",
          ],
        },
        {
          heading: "5.4 User Indemnification",
          body: [
            "You agree to indemnify, defend, and hold harmless LawMate, its officers, directors, employees, and affiliates from any claims, damages, losses, or expenses (including reasonable attorneys' fees) arising from:",
          ],
          bullets: [
            "Your violation of these Terms;",
            "Your misuse of the Platform or Your Data;",
            "Your violation of applicable laws, professional ethics rules, or third-party rights;",
            "Any claims by your clients arising from your use of the Platform.",
          ],
        },
      ],
    },
    {
      heading: "6. DATA SECURITY AND MULTI-TENANT ARCHITECTURE",
      body: [],
      subsections: [
        {
          heading: "6.1 Multi-Tenant Security Model",
          body: ["The Platform employs a secure multi-tenant architecture with strict per-user data isolation. Each user's data is logically and physically segregated using:"],
          bullets: [
            "User-specific storage partitions in AWS S3 with unique access keys;",
            "Encryption at rest (AES-256) and in transit (TLS 1.2+);",
            "Role-based access controls (RBAC) ensuring no cross-user access;",
            "Isolated AI processing contexts in AWS Bedrock per user session;",
            "Comprehensive audit logging of all data access and processing activities.",
          ],
        },
        {
          heading: "6.2 No Cross-User Data Exposure",
          body: ["Our technical safeguards guarantee that:"],
          bullets: [
            "One lawyer's case files are never accessible to any other lawyer;",
            "AI models process only one user's data at a time, with no data leakage between sessions;",
            "No aggregated or anonymized datasets are created from user data;",
            "All data processing complies with the principle of purpose limitation under Indian privacy law.",
          ],
        },
        {
          heading: "6.3 User Responsibility for Account Security",
          body: [
            "You are responsible for maintaining the confidentiality of your login credentials and for all activities conducted through your account. You must immediately notify us of any unauthorized access or security breach.",
          ],
        },
        {
          heading: "6.4 Data Breach Notification",
          body: [
            "In the event of a data breach affecting Your Data, we will notify you within seventy-two (72) hours of becoming aware of the breach, in accordance with the Information Technology Act, 2000 and applicable data protection regulations.",
          ],
        },
      ],
    },
    {
      heading: "7. DATA RETENTION, DELETION, AND PORTABILITY",
      body: [],
      subsections: [
        {
          heading: "7.1 Retention Policy",
          body: [
            "We retain Your Data for as long as your account remains active and for ninety (90) days thereafter, unless you request earlier deletion. Backup copies may be retained for up to one hundred eighty (180) days for disaster recovery purposes.",
          ],
        },
        {
          heading: "7.2 Right to Deletion",
          body: [
            "You may request deletion of Your Data at any time by contacting us at support@lawmate.in. We will delete Your Data within thirty (30) days of your request, except where retention is required by law or ongoing legal obligations.",
          ],
        },
        {
          heading: "7.3 Data Portability",
          body: [
            "You may request an export of Your Data in machine-readable format (JSON or CSV) at any time. We will provide the export within fifteen (15) business days of your request.",
          ],
        },
        {
          heading: "7.4 Account Termination",
          body: [
            "Upon termination of your account (by you or by us), Your Data will be deleted in accordance with Section 7.1. You are responsible for exporting any data you wish to retain before terminating your account.",
          ],
        },
      ],
    },
    {
      heading: "8. ACCEPTABLE USE AND PROHIBITED ACTIVITIES",
      body: [],
      subsections: [
        {
          heading: "8.1 Prohibited Uses",
          body: ["You may not:"],
          bullets: [
            "Use the Platform for any unlawful purpose or in violation of professional ethics rules;",
            "Attempt to access another user's data or account;",
            "Reverse engineer, decompile, or disassemble any part of the Platform;",
            "Introduce malware, viruses, or any harmful code;",
            "Overload or disrupt the Platform's servers or infrastructure;",
            "Scrape, harvest, or collect user data without authorization;",
            "Use the Platform to facilitate fraud, money laundering, or other criminal activities.",
          ],
        },
        {
          heading: "8.2 Enforcement",
          body: [
            "We reserve the right to investigate violations of these Terms and to take appropriate action, including account suspension, termination, and reporting to law enforcement authorities.",
          ],
        },
      ],
    },
    {
      heading: "9. THIRD-PARTY SERVICES AND INTEGRATIONS",
      body: [],
      subsections: [
        {
          heading: "9.1 AWS Infrastructure",
          body: [
            "The Platform utilizes Amazon Web Services (AWS) for cloud storage (S3) and AI processing (Bedrock). AWS's terms of service and data processing agreements apply to their services. We have executed appropriate data processing agreements with AWS to ensure compliance with Indian data protection laws.",
          ],
        },
        {
          heading: "9.2 No Third-Party Liability",
          body: [
            "While we select reputable third-party providers, we are not responsible for the acts, omissions, or failures of third-party services. Your use of integrated third-party services may be subject to their separate terms and conditions.",
          ],
        },
        {
          heading: "9.3 Future Kerala High Court Integration",
          body: [
            "In the event that we enter into a Memorandum of Understanding (MoU) with the Kerala High Court to access private court APIs or systems, we will update these Terms to reflect any additional rights, obligations, or data processing arrangements. Such updates will be notified to you in accordance with Section 12.",
          ],
        },
      ],
    },
    {
      heading: "10. FEES, PAYMENT, AND SUBSCRIPTION",
      body: [],
      subsections: [
        {
          heading: "10.1 Subscription Fees",
          body: [
            "Use of the Platform requires payment of subscription fees as specified in your selected pricing plan. All fees are in Indian Rupees (INR) and exclude applicable goods and services tax (GST), which will be added at checkout.",
          ],
        },
        {
          heading: "10.2 Payment Terms",
          body: [
            "Subscription fees are billed in advance on a monthly or annual basis (as selected). Payment must be made by credit card, debit card, UPI, or other authorized payment methods. Failure to pay fees may result in suspension or termination of service.",
          ],
        },
        {
          heading: "10.3 Refund Policy",
          body: [
            "Subscription fees are generally non-refundable. However, we may provide pro-rata refunds in cases of early termination due to service unavailability or material breach by LawMate. Refund requests must be submitted in writing to billing@lawmate.in.",
          ],
        },
        {
          heading: "10.4 Price Changes",
          body: [
            "We reserve the right to modify subscription fees upon thirty (30) days' written notice. Continued use of the Platform after the notice period constitutes acceptance of the new fees.",
          ],
        },
      ],
    },
    {
      heading: "11. GOVERNING LAW AND DISPUTE RESOLUTION",
      body: [],
      subsections: [
        {
          heading: "11.1 Governing Law",
          body: [
            "These Terms are governed by and construed in accordance with the laws of India, including the Information Technology Act, 2000, the Indian Contract Act, 1872, and applicable rules and regulations. The courts of Ernakulam, Kerala shall have exclusive jurisdiction over any disputes arising under these Terms.",
          ],
        },
        {
          heading: "11.2 Dispute Resolution",
          body: ["Any dispute, controversy, or claim arising out of or relating to these Terms shall be resolved through the following process:"],
          bullets: [
            "Negotiation: The parties shall attempt to resolve the dispute through good faith negotiations for thirty (30) days;",
            "Mediation: If negotiation fails, the dispute shall be referred to mediation under the auspices of the Kerala High Court Mediation Centre;",
            "Arbitration: If mediation fails, the dispute shall be referred to arbitration in accordance with the Arbitration and Conciliation Act, 1996, with the seat of arbitration in Ernakulam, Kerala.",
          ],
        },
        {
          heading: "11.3 Injunctive Relief",
          body: [
            "Notwithstanding the above, either party may seek injunctive relief or other equitable remedies from a court of competent jurisdiction to prevent irreparable harm.",
          ],
        },
      ],
    },
    {
      heading: "12. MODIFICATIONS TO THESE TERMS",
      body: [],
      subsections: [
        {
          heading: "12.1 Right to Modify",
          body: [
            "We reserve the right to modify these Terms at any time. Material changes will be notified to you via email or prominent notice on the Platform at least thirty (30) days before the changes take effect.",
          ],
        },
        {
          heading: "12.2 Acceptance of Changes",
          body: [
            "Your continued use of the Platform after the effective date of modified Terms constitutes acceptance of the changes. If you do not agree to the modified Terms, you must discontinue use of the Platform and may request account termination and data deletion.",
          ],
        },
      ],
    },
    {
      heading: "13. GENERAL PROVISIONS",
      body: [],
      subsections: [
        {
          heading: "13.1 Entire Agreement",
          body: [
            "These Terms, together with the Privacy Policy, constitute the entire agreement between you and LawMate regarding your use of the Platform and supersede all prior agreements and understandings.",
          ],
        },
        {
          heading: "13.2 Severability",
          body: [
            "If any provision of these Terms is found to be invalid or unenforceable, the remaining provisions shall remain in full force and effect.",
          ],
        },
        {
          heading: "13.3 Waiver",
          body: [
            "No waiver of any provision of these Terms shall be deemed a further or continuing waiver of such provision or any other provision.",
          ],
        },
        {
          heading: "13.4 Assignment",
          body: [
            "You may not assign or transfer these Terms or your account without our prior written consent. We may assign these Terms without restriction.",
          ],
        },
        {
          heading: "13.5 Force Majeure",
          body: [
            "Neither party shall be liable for any failure or delay in performance due to circumstances beyond its reasonable control, including acts of God, natural disasters, war, terrorism, pandemics, or government actions.",
          ],
        },
        {
          heading: "13.6 Relationship",
          body: [
            "Nothing in these Terms creates a partnership, joint venture, agency, or employment relationship between you and LawMate.",
          ],
        },
      ],
    },
    {
      heading: "14. CONTACT INFORMATION",
      body: [
        "For questions, concerns, or notices regarding these Terms, please contact us at:",
        "LawMate · Email: legal@lawmate.in · Support: support@lawmate.in · Address: [To be updated with registered office address]",
      ],
    },
  ],
  acknowledgment:
    'BY CLICKING "I AGREE," CREATING AN ACCOUNT, OR USING THE PLATFORM, YOU ACKNOWLEDGE THAT YOU HAVE READ, UNDERSTOOD, AND AGREE TO BE BOUND BY THESE TERMS OF USE.',
};
