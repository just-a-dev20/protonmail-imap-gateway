// SPDX-License-Identifier: GPL-3.0-or-later
package protonmail

import (
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGatewayAPIRejection(t *testing.T) {
	for _, code := range []int{10004, 9001} {
		t.Run(fmt.Sprint(code), func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusForbidden)
				fmt.Fprintf(w, `{"Code":%d,"Error":"access denied"}`, code)
			}))
			defer server.Close()
			client := &Client{RootURL: server.URL, AppVersion: "Other", HTTPClient: server.Client()}
			info, err := client.AuthInfo("test-user")
			var apiError *APIError
			if info != nil || !errors.As(err, &apiError) || apiError.Code != code {
				t.Fatalf("rejection became success or lost its code: %v", err)
			}
		})
	}
}
