import 'dotenv/config';
export const JWT_SECRET = process.env.JWT_SECRET || 'dev-jwt-secret-change-me';
export const JWT_ISSUER = process.env.JWT_ISSUER || 'yolo-llm-mvp';