import { safeStorage } from 'electron';
import fs from 'node:fs/promises';
import path from 'node:path';

export type AppSecrets = {
  ai33Key: string;
  aimaxKey: string;
};

type EncryptedSecrets = Partial<Record<keyof AppSecrets, string>>;
const EMPTY_SECRETS: AppSecrets = { ai33Key: '', aimaxKey: '' };

export class SecretStore {
  private readonly filePath: string;

  constructor(userDataPath: string) {
    this.filePath = path.join(userDataPath, 'api-secrets.enc.json');
  }

  private async readEncrypted(): Promise<EncryptedSecrets> {
    try {
      return JSON.parse(await fs.readFile(this.filePath, 'utf8')) as EncryptedSecrets;
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (code === 'ENOENT' || error instanceof SyntaxError) return {};
      throw error;
    }
  }

  async getAll(): Promise<AppSecrets> {
    const encrypted = await this.readEncrypted();
    const result = { ...EMPTY_SECRETS };
    if (!safeStorage.isEncryptionAvailable()) return result;
    for (const key of Object.keys(result) as (keyof AppSecrets)[]) {
      const value = encrypted[key];
      if (!value) continue;
      try {
        result[key] = safeStorage.decryptString(Buffer.from(value, 'base64'));
      } catch {
        // Ignore values encrypted for a different Windows account or machine.
      }
    }
    return result;
  }

  async merge(values: Partial<AppSecrets>): Promise<AppSecrets> {
    const supplied = Object.entries(values).filter(
      (entry): entry is [keyof AppSecrets, string] => Boolean(entry[1]?.trim()),
    );
    if (!supplied.length) return this.getAll();
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error('Windows không cung cấp kho mã hóa an toàn cho API key.');
    }
    const encrypted = await this.readEncrypted();
    for (const [key, raw] of supplied) {
      encrypted[key] = safeStorage.encryptString(raw.trim()).toString('base64');
    }
    await fs.mkdir(path.dirname(this.filePath), { recursive: true });
    const temporary = `${this.filePath}.tmp`;
    await fs.writeFile(temporary, JSON.stringify(encrypted, null, 2), 'utf8');
    await fs.rename(temporary, this.filePath);
    return this.getAll();
  }
}
