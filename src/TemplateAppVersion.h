#ifndef _TEMPLATEAPPVERSION_H_
#define _TEMPLATEAPPVERSION_H_

// The version, and the only place it is written. A release is a pushed tag
// v<TEMPLATEAPP_VERSION>; .github/workflows/release.yml refuses any other tag,
// and tools/make-release/ stamps it into the packaged Info.plist.
#define TEMPLATEAPP_VERSION "0.1.0"

#endif
