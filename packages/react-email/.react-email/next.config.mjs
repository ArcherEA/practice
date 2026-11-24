
import path from 'path';
const emailsDirRelativePath = path.normalize('./emails');
const userProjectLocation = 'G:/GithubRepos/PRODUCT/.claude/worktrees/agent-adefb186abdf141fb/packages/react-email';
const previewServerLocation = 'G:/GithubRepos/PRODUCT/.claude/worktrees/agent-adefb186abdf141fb/packages/react-email/.react-email';
const rootDir = 'G:/GithubRepos/PRODUCT/.claude/worktrees/agent-adefb186abdf141fb';
/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_IS_BUILDING: 'true',
    REACT_EMAIL_INTERNAL_EMAILS_DIR_RELATIVE_PATH: emailsDirRelativePath,
    REACT_EMAIL_INTERNAL_EMAILS_DIR_ABSOLUTE_PATH: path.resolve(userProjectLocation, emailsDirRelativePath),
    REACT_EMAIL_INTERNAL_PREVIEW_SERVER_LOCATION: previewServerLocation,
    REACT_EMAIL_INTERNAL_USER_PROJECT_LOCATION: userProjectLocation,
    
  },
  turbopack: {
    root: rootDir,
  },
  outputFileTracingRoot: rootDir,
  serverExternalPackages: ['esbuild', 'jiti'],
  typescript: {
    ignoreBuildErrors: true
  },
  staticPageGenerationTimeout: 600,
}

export default nextConfig