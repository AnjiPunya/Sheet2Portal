export type Permission =
  | 'view'
  | 'workbooks:upload'
  | 'workbooks:edit'
  | 'records:create'
  | 'records:edit'
  | 'records:delete'
  | 'records:approve'

export interface CurrentUser {
  id: string
  email: string
  display_name: string
  role: string
  permissions: Permission[]
}
