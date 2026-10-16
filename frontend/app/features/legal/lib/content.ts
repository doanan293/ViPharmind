import type { Language } from "~/i18n/config"

export type LegalDocument = "privacy" | "terms"

export interface LegalSection {
  heading: string
  paragraphs: string[]
}

export interface LegalText {
  title: string
  description: string
  updated: string
  sections: LegalSection[]
}

/** Paths of each legal page; Vietnamese has no prefix, like the landing page. */
export const LEGAL_PATHS: Record<LegalDocument, Record<Language, string>> = {
  privacy: { vi: "/privacy", en: "/en/privacy" },
  terms: { vi: "/terms", en: "/en/terms" },
}

export const LEGAL_LINK_LABELS: Record<
  LegalDocument,
  Record<Language, string>
> = {
  privacy: { vi: "Chính sách quyền riêng tư", en: "Privacy policy" },
  terms: { vi: "Điều khoản sử dụng", en: "Terms of use" },
}

const UPDATED = "2026-10-10"

export const LEGAL_TEXT: Record<LegalDocument, Record<Language, LegalText>> = {
  privacy: {
    vi: {
      title: "Chính sách quyền riêng tư",
      description:
        "ViPharmind lưu những dữ liệu nào, lưu ở đâu và ai được đọc chúng.",
      updated: UPDATED,
      sections: [
        {
          heading: "Dữ liệu chúng tôi lưu",
          paragraphs: [
            "Tài khoản: tên hiển thị, email, số điện thoại nếu bạn thêm, mật khẩu đã băm và liên kết Google nếu bạn đăng nhập bằng Google.",
            "Hội thoại: câu hỏi, câu trả lời, nguồn đã trích và phản hồi bạn gửi.",
            "Nội dung bạn nạp: tài liệu, thuật ngữ và tên gọi dân gian trong các bộ tài liệu của bạn hoặc tổ chức của bạn.",
            "Nhật ký hoạt động: các thao tác thay đổi tổ chức và bộ tài liệu (ai làm gì, lúc nào), để thành viên thấy thay đổi của nhau.",
          ],
        },
        {
          heading: "Dữ liệu được lưu ở đâu",
          paragraphs: [
            "Cơ sở dữ liệu chạy trên Neon (Postgres, khu vực Singapore). Chỉ mục tìm kiếm vector chạy trên Qdrant Cloud. Máy chủ ứng dụng và giao diện web chạy trên Vercel (khu vực Singapore).",
            "Câu hỏi và các đoạn tài liệu liên quan được gửi qua OpenRouter tới nhà cung cấp mô hình để chạy mô hình ngôn ngữ, mô hình embedding và mô hình xếp hạng lại. OpenRouter và nhà cung cấp đó xử lý dữ liệu để trả kết quả cho từng yêu cầu.",
          ],
        },
        {
          heading: "Ai được đọc dữ liệu của bạn",
          paragraphs: [
            "Bạn đọc được hội thoại và nội dung của mình. Thành viên tổ chức đọc được các bộ tài liệu của tổ chức theo vai trò của họ. Bộ tài liệu công khai thì mọi người dùng đều tìm được.",
            "Quản trị viên hệ thống có thể đọc hội thoại, tài khoản và nội dung đã nạp để vận hành, xử lý sự cố và ngăn lạm dụng. Việc đọc này không được ghi vào nhật ký hoạt động.",
          ],
        },
        {
          heading: "Nội dung bạn nạp",
          paragraphs: [
            "Nội dung bạn nạp thuộc về người dùng hoặc tổ chức đã nạp nó. ViPharmind chỉ dùng nội dung đó để trả lời câu hỏi của những người được phép thấy bộ tài liệu.",
          ],
        },
        {
          heading: "Email và tin nhắn",
          paragraphs: [
            "Email được dùng để gửi mã xác minh, mã đăng nhập, mã đặt lại mật khẩu và lời mời vào tổ chức. Chúng tôi không gửi quảng cáo.",
          ],
        },
        {
          heading: "Xoá dữ liệu",
          paragraphs: [
            "Bạn có thể xoá hội thoại và bộ tài liệu của mình bất cứ lúc nào. Bộ tài liệu đã xoá không còn được tìm kiếm và được dọn hẳn sau một thời gian ngắn. Để xoá tài khoản, hãy liên hệ quản trị viên.",
          ],
        },
      ],
    },
    en: {
      title: "Privacy policy",
      description:
        "What ViPharmind stores, where it is stored and who can read it.",
      updated: UPDATED,
      sections: [
        {
          heading: "What we store",
          paragraphs: [
            "Account: display name, email, phone number if you add one, a hashed password and your Google link if you sign in with Google.",
            "Conversations: your questions, the answers, the cited sources and the feedback you send.",
            "Content you upload: documents, glossary terms and colloquial names in your own or your organization's collections.",
            "Activity log: changes to organizations and collections (who did what, and when), so members can see each other's changes.",
          ],
        },
        {
          heading: "Where data is stored",
          paragraphs: [
            "The database runs on Neon (Postgres, Singapore region). The vector search index runs on Qdrant Cloud. The application server and the web interface run on Vercel (Singapore region).",
            "Questions and the relevant document passages are sent through OpenRouter to the model providers that run the language, embedding and reranking models; OpenRouter and those providers process the data to answer each request.",
          ],
        },
        {
          heading: "Who can read your data",
          paragraphs: [
            "You can read your own conversations and content. Organization members can read the organization's collections according to their role. Public collections are searchable by every user.",
            "System administrators can read conversations, accounts and uploaded content to operate the service, fix problems and prevent abuse. This reading is not recorded in the activity log.",
          ],
        },
        {
          heading: "Content you upload",
          paragraphs: [
            "Content you upload belongs to the user or organization that uploaded it. ViPharmind uses it only to answer the questions of people allowed to see the collection.",
          ],
        },
        {
          heading: "Email and messages",
          paragraphs: [
            "Email is used to send verification, sign-in and password reset codes and organization invitations. We do not send marketing.",
          ],
        },
        {
          heading: "Deleting data",
          paragraphs: [
            "You can delete your conversations and collections at any time. A deleted collection is no longer searched and is purged shortly after. To delete your account, contact an administrator.",
          ],
        },
      ],
    },
  },
  terms: {
    vi: {
      title: "Điều khoản sử dụng",
      description: "Điều kiện khi dùng ViPharmind để tra cứu thông tin thuốc.",
      updated: UPDATED,
      sections: [
        {
          heading: "Câu trả lời của hệ thống",
          paragraphs: [
            "ViPharmind trả lời dựa trên các bộ tài liệu bạn được phép thấy và luôn ghi nguồn. Câu trả lời không thay thế tư vấn của dược sĩ hoặc bác sĩ. Hãy kiểm tra nguồn được trích trước khi dùng thông tin cho người bệnh.",
          ],
        },
        {
          heading: "Tài khoản",
          paragraphs: [
            "Bạn chịu trách nhiệm giữ an toàn thông tin đăng nhập của mình. Mỗi tài khoản dành cho một người.",
            "Tài khoản có thể bị khoá nếu vi phạm các điều khoản này hoặc gây hại cho hệ thống và người dùng khác.",
          ],
        },
        {
          heading: "Nội dung bạn nạp",
          paragraphs: [
            "Chỉ nạp nội dung bạn có quyền sử dụng. Cấm nạp nội dung vi phạm bản quyền, nội dung sai lệch có chủ ý về thuốc, mã độc hoặc dữ liệu cá nhân của người khác khi không được phép.",
            "Bạn giữ quyền với nội dung của mình. Bạn cho phép ViPharmind lưu và xử lý nội dung đó để trả lời câu hỏi của những người được phép thấy bộ tài liệu.",
          ],
        },
        {
          heading: "Hạn mức và thay đổi dịch vụ",
          paragraphs: [
            "Mỗi người dùng và tổ chức có hạn mức về dung lượng nội dung và số bộ tài liệu. Dịch vụ đang ở giai đoạn đầu, có thể thay đổi hoặc tạm dừng. Khi điều khoản thay đổi, ngày cập nhật ở đầu trang sẽ đổi theo.",
          ],
        },
      ],
    },
    en: {
      title: "Terms of use",
      description:
        "The conditions for using ViPharmind to look up drug information.",
      updated: UPDATED,
      sections: [
        {
          heading: "The system's answers",
          paragraphs: [
            "ViPharmind answers from the collections you are allowed to see and always cites its sources. Its answers do not replace advice from a pharmacist or doctor. Check the cited sources before using the information for a patient.",
          ],
        },
        {
          heading: "Accounts",
          paragraphs: [
            "You are responsible for keeping your sign-in details safe. Each account is for one person.",
            "An account may be disabled if it breaks these terms or harms the system or other users.",
          ],
        },
        {
          heading: "Content you upload",
          paragraphs: [
            "Only upload content you have the right to use. Do not upload content that infringes copyright, deliberately wrong drug information, malware or other people's personal data without permission.",
            "You keep the rights to your content. You allow ViPharmind to store and process it to answer the questions of people allowed to see the collection.",
          ],
        },
        {
          heading: "Quotas and changes to the service",
          paragraphs: [
            "Each user and organization has a quota for content size and number of collections. The service is at an early stage and may change or pause. When these terms change, the date at the top changes too.",
          ],
        },
      ],
    },
  },
}
