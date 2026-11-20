import { NextRequest } from "next/server";
import { proxyBackend } from "@/server/backendProxy";

export const dynamic = "force-dynamic";

type RouteContext = { params: { path: string[] } };

export function GET(request: NextRequest, context: RouteContext) {
  return proxyBackend(request, context.params.path);
}

export function POST(request: NextRequest, context: RouteContext) {
  return proxyBackend(request, context.params.path);
}

export function PUT(request: NextRequest, context: RouteContext) {
  return proxyBackend(request, context.params.path);
}

export function PATCH(request: NextRequest, context: RouteContext) {
  return proxyBackend(request, context.params.path);
}

export function DELETE(request: NextRequest, context: RouteContext) {
  return proxyBackend(request, context.params.path);
}
