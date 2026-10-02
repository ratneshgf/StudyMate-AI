import { cpSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
const output = 'vercel-public';
rmSync(output, { recursive: true, force: true });
mkdirSync(output, { recursive: true });
cpSync('static', join(output, 'static'), { recursive: true });
console.log('StudyMate frontend assets prepared for Vercel.');
