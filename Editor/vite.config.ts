import path from "path"
import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
    const commonConfig = {
        plugins: [react()],
        base: '/editor/',  // Match the FastAPI mount point
        resolve: {
            alias: {
                "@": path.resolve(__dirname, "./@"),
            },
        },
        optimizeDeps: {
            include: ['pdfjs-dist']
        },
        server: {
            proxy: {
                '/api': 'http://localhost:8000',
                '/ws': {
                    target: 'ws://localhost:8000',
                    ws: true
                }
            }
        }
    }

    // Development-specific config
    if (mode === 'development') {
        return {
            ...commonConfig,
            build: {
                outDir: '../Backend/static/editor',
                emptyOutDir: true,
                minify: false,
                sourcemap: true,
                rollupOptions: {
                    input: {
                        main: path.resolve(__dirname, 'index.html'),
                        'pdf.worker': 'pdfjs-dist/build/pdf.worker.mjs',
                    },
                    output: {
                        entryFileNames: '[name].bundle.js',
                    }
                }
            }
        }
    }

    // Production config
    return {
        ...commonConfig,
        build: {
            outDir: '../Backend/static/editor',
            emptyOutDir: true,
            rollupOptions: {
                input: {
                    main: path.resolve(__dirname, 'index.html'),
                    'pdf.worker': 'pdfjs-dist/build/pdf.worker.mjs',
                },
                output: {
                    entryFileNames: '[name].bundle.js',
                }
            }
        }
    }
})
