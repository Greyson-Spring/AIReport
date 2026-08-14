import http from './http'

export const getAccountPoolStatus = () => http.get('/wx/account-pool/status')
export const getAccounts = () => http.get('/wx/account-pool/accounts')
export const addAccount = () => http.post('/wx/account-pool/add')
export const removeAccount = (port: number) => http.post('/wx/account-pool/remove', { port })
